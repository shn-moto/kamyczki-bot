"""Modal.com serverless ML service for CLIP + rembg inference."""

import modal

# Define the Modal app
app = modal.App("kamyczki-ml")

# Image with all ML dependencies
ml_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "torch",
        "open-clip-torch",
        "rembg[gpu]",
        "pillow",
        "numpy<2",
    )
    .run_commands(
        # Pre-download models during image build
        "python -c 'import open_clip; open_clip.create_model_and_transforms(\"ViT-B-32\", pretrained=\"laion2b_s34b_b79k\")'",
        "python -c 'from rembg import new_session; new_session(\"u2net\")'",
    )
)


@app.cls(
    image=ml_image,
    gpu="T4",  # Cheapest GPU, sufficient for CLIP
    container_idle_timeout=60,  # Keep warm for 60 seconds
    allow_concurrent_inputs=10,  # Handle multiple requests
)
class MLService:
    """Serverless ML service for stone detection and embedding."""

    @modal.enter()
    def load_models(self):
        """Load models when container starts."""
        import torch
        import open_clip
        from rembg import new_session

        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        # Load CLIP
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(
            "ViT-B-32", pretrained="laion2b_s34b_b79k"
        )
        self.model = self.model.to(self.device)
        self.model.eval()
        self.tokenizer = open_clip.get_tokenizer("ViT-B-32")

        # Pre-compute text embeddings for stone detection
        self.stone_prompts = [
            "a painted stone with artwork",
            "a decorated rock with drawing",
            "a stone with painted picture",
            "hand painted pebble art",
            "rock painting craft",
        ]
        self.not_stone_prompts = [
            "a photograph of a person",
            "a screenshot of text",
            "a blank white image",
        ]

        with torch.no_grad():
            stone_tokens = self.tokenizer(self.stone_prompts).to(self.device)
            not_stone_tokens = self.tokenizer(self.not_stone_prompts).to(self.device)
            self.stone_text_features = self.model.encode_text(stone_tokens)
            self.not_stone_text_features = self.model.encode_text(not_stone_tokens)
            self.stone_text_features /= self.stone_text_features.norm(dim=-1, keepdim=True)
            self.not_stone_text_features /= self.not_stone_text_features.norm(dim=-1, keepdim=True)

        # Load rembg session
        self.rembg_session = new_session("u2net")

    @modal.method()
    def process_image(self, image_bytes: bytes) -> dict:
        """Process image: crop stone, detect if valid, return embedding.

        Returns:
            {
                "is_stone": bool,
                "confidence": float,
                "embedding": list[float] | None,
                "cropped_image": bytes | None,
                "thumbnail": bytes | None,
            }
        """
        import torch
        from PIL import Image
        from io import BytesIO
        from rembg import remove

        # Step 1: Smart crop with rembg
        image = Image.open(BytesIO(image_bytes)).convert("RGBA")
        result = remove(image, session=self.rembg_session)

        bbox = result.getbbox()
        if not bbox:
            return {
                "is_stone": False,
                "confidence": 0.0,
                "embedding": None,
                "cropped_image": None,
                "thumbnail": None,
            }

        # Crop with padding
        padding = 20
        x1, y1, x2, y2 = bbox
        x1 = max(0, x1 - padding)
        y1 = max(0, y1 - padding)
        x2 = min(result.width, x2 + padding)
        y2 = min(result.height, y2 + padding)

        original = Image.open(BytesIO(image_bytes)).convert("RGB")
        cropped = original.crop((x1, y1, x2, y2))

        # Save cropped image
        output = BytesIO()
        cropped.save(output, format="JPEG", quality=90)
        cropped_bytes = output.getvalue()

        # Create thumbnail
        thumbnail = cropped.copy()
        thumbnail.thumbnail((200, 200), Image.LANCZOS)
        thumb_output = BytesIO()
        thumbnail.save(thumb_output, format="JPEG", quality=85)
        thumbnail_bytes = thumb_output.getvalue()

        # Step 2: Stone detection with CLIP
        image_input = self.preprocess(cropped).unsqueeze(0).to(self.device)

        with torch.no_grad():
            image_features = self.model.encode_image(image_input)
            image_features /= image_features.norm(dim=-1, keepdim=True)

            stone_similarity = (image_features @ self.stone_text_features.T).mean().item()
            not_stone_similarity = (image_features @ self.not_stone_text_features.T).mean().item()

        score = stone_similarity - not_stone_similarity
        is_stone = score > 0.05

        if not is_stone:
            return {
                "is_stone": False,
                "confidence": score,
                "embedding": None,
                "cropped_image": cropped_bytes,
                "thumbnail": thumbnail_bytes,
            }

        # Step 3: Get embedding for stone matching
        embedding = image_features.cpu().numpy().flatten().tolist()

        return {
            "is_stone": True,
            "confidence": score,
            "embedding": embedding,
            "cropped_image": cropped_bytes,
            "thumbnail": thumbnail_bytes,
        }

    @modal.method()
    def get_embedding(self, image_bytes: bytes) -> list[float]:
        """Get CLIP embedding for an image (512 dimensions)."""
        import torch
        from PIL import Image
        from io import BytesIO

        image = Image.open(BytesIO(image_bytes)).convert("RGB")
        image_input = self.preprocess(image).unsqueeze(0).to(self.device)

        with torch.no_grad():
            image_features = self.model.encode_image(image_input)
            image_features /= image_features.norm(dim=-1, keepdim=True)

        return image_features.cpu().numpy().flatten().tolist()

    @modal.method()
    def health_check(self) -> dict:
        """Health check endpoint."""
        import torch
        return {
            "status": "ok",
            "device": self.device,
            "cuda_available": torch.cuda.is_available(),
        }


# Web endpoint for external access
@app.function(image=ml_image)
@modal.web_endpoint(method="POST")
def process_image_api(image_base64: str) -> dict:
    """HTTP endpoint for processing images.

    Accepts base64-encoded image, returns processing result.
    """
    import base64

    image_bytes = base64.b64decode(image_base64)
    service = MLService()
    result = service.process_image.remote(image_bytes)

    # Encode binary data as base64 for JSON response
    if result["cropped_image"]:
        result["cropped_image"] = base64.b64encode(result["cropped_image"]).decode()
    if result["thumbnail"]:
        result["thumbnail"] = base64.b64encode(result["thumbnail"]).decode()

    return result


# For local testing
if __name__ == "__main__":
    # Deploy with: modal deploy modal_app.py
    # Test locally with: modal run modal_app.py
    print("Modal app ready. Deploy with: modal deploy modal_app.py")
