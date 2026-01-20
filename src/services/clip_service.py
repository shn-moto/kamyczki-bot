import logging
import torch
import open_clip
from PIL import Image
from io import BytesIO
import numpy as np

logger = logging.getLogger(__name__)


class CLIPService:
    def __init__(self):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(
            "ViT-B-32", pretrained="laion2b_s34b_b79k"
        )
        self.model = self.model.to(self.device)
        self.model.eval()
        self.tokenizer = open_clip.get_tokenizer("ViT-B-32")

        # Text prompts for stone detection
        self.stone_prompts = [
            "a painted stone with artwork",
            "a decorated rock with drawing",
            "a stone with painted picture",
            "hand painted pebble art",
            "rock painting craft",
            "decorated stone with dragonfly",
            "painted rock with flowers",
        ]
        self.not_stone_prompts = [
            "a photograph of a person",
            "a screenshot of text",
            "a blank white image",
        ]

        # Pre-compute text embeddings
        with torch.no_grad():
            stone_tokens = self.tokenizer(self.stone_prompts).to(self.device)
            not_stone_tokens = self.tokenizer(self.not_stone_prompts).to(self.device)
            self.stone_text_features = self.model.encode_text(stone_tokens)
            self.not_stone_text_features = self.model.encode_text(not_stone_tokens)
            self.stone_text_features /= self.stone_text_features.norm(dim=-1, keepdim=True)
            self.not_stone_text_features /= self.not_stone_text_features.norm(dim=-1, keepdim=True)

    def is_stone(self, image_bytes: bytes, threshold: float = 0.05) -> tuple[bool, float]:
        """Check if image contains a painted stone.

        Returns (is_stone, confidence_score)
        """
        image = Image.open(BytesIO(image_bytes)).convert("RGB")
        image_input = self.preprocess(image).unsqueeze(0).to(self.device)

        with torch.no_grad():
            image_features = self.model.encode_image(image_input)
            image_features /= image_features.norm(dim=-1, keepdim=True)

            # Compare with stone prompts
            stone_similarity = (image_features @ self.stone_text_features.T).mean().item()
            not_stone_similarity = (image_features @ self.not_stone_text_features.T).mean().item()

        score = stone_similarity - not_stone_similarity
        logger.info(f"Stone detection: stone_sim={stone_similarity:.4f}, not_stone_sim={not_stone_similarity:.4f}, score={score:.4f}, threshold={threshold}")
        return score > threshold, score

    def get_embedding(self, image_bytes: bytes) -> list[float]:
        """Get CLIP embedding for image (512 dimensions)."""
        image = Image.open(BytesIO(image_bytes)).convert("RGB")
        image_input = self.preprocess(image).unsqueeze(0).to(self.device)

        with torch.no_grad():
            image_features = self.model.encode_image(image_input)
            image_features /= image_features.norm(dim=-1, keepdim=True)

        return image_features.cpu().numpy().flatten().tolist()

    def encode_text_query(self, text: str) -> list[float]:
        """Encode text query to embedding for semantic search (512 dimensions).

        Used for text-to-image search: find stones matching a description.
        """
        tokens = self.tokenizer([text]).to(self.device)
        with torch.no_grad():
            text_features = self.model.encode_text(tokens)
            text_features /= text_features.norm(dim=-1, keepdim=True)
        return text_features.cpu().numpy().flatten().tolist()

    def smart_crop_stone(self, image_bytes: bytes) -> tuple[bytes, bytes] | None:
        """Умный кроп камня через удаление фона (rembg).

        Returns: (cropped_bytes, thumbnail_bytes) или None если объект не найден
        """
        from rembg import remove

        image = Image.open(BytesIO(image_bytes)).convert("RGBA")

        # Удаляем фон
        result = remove(image)

        # Получаем bounding box непрозрачных пикселей
        bbox = result.getbbox()
        if not bbox:
            logger.warning("smart_crop_stone: no object found (empty bbox)")
            return None

        # Кропим с небольшим padding
        padding = 20
        x1, y1, x2, y2 = bbox
        x1 = max(0, x1 - padding)
        y1 = max(0, y1 - padding)
        x2 = min(result.width, x2 + padding)
        y2 = min(result.height, y2 + padding)

        logger.info(f"smart_crop_stone: bbox={bbox}, padded=({x1},{y1},{x2},{y2})")

        # Кропим оригинал (RGB) по найденным границам
        original = Image.open(BytesIO(image_bytes)).convert("RGB")
        cropped = original.crop((x1, y1, x2, y2))

        # Сохраняем кроп
        output = BytesIO()
        cropped.save(output, format="JPEG", quality=90)
        cropped_bytes = output.getvalue()

        # Создаем миниатюру 200x200
        thumbnail = cropped.copy()
        thumbnail.thumbnail((200, 200), Image.LANCZOS)
        thumb_output = BytesIO()
        thumbnail.save(thumb_output, format="JPEG", quality=85)
        thumbnail_bytes = thumb_output.getvalue()

        return cropped_bytes, thumbnail_bytes

    def crop_to_center(self, image_bytes: bytes, ratio: float = 0.7) -> bytes:
        """Crop image to center region (simple crop for stone focus)."""
        image = Image.open(BytesIO(image_bytes)).convert("RGB")
        width, height = image.size

        new_width = int(width * ratio)
        new_height = int(height * ratio)
        left = (width - new_width) // 2
        top = (height - new_height) // 2

        cropped = image.crop((left, top, left + new_width, top + new_height))

        output = BytesIO()
        cropped.save(output, format="JPEG", quality=85)
        return output.getvalue()


# Singleton instance
_clip_service = None


def get_clip_service() -> CLIPService:
    global _clip_service
    if _clip_service is None:
        _clip_service = CLIPService()
    return _clip_service
