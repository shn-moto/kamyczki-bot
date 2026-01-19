"""Modal.com API client for serverless ML inference."""

import base64
import logging
import httpx
from src.config import settings

logger = logging.getLogger(__name__)

# Modal web endpoint URL (set after deployment)
MODAL_ENDPOINT = settings.modal_endpoint_url if hasattr(settings, 'modal_endpoint_url') else None


async def process_image_remote(image_bytes: bytes) -> dict:
    """Process image using Modal serverless ML service.

    Args:
        image_bytes: Raw image bytes

    Returns:
        {
            "is_stone": bool,
            "confidence": float,
            "embedding": list[float] | None,
            "cropped_image": bytes | None,
            "thumbnail": bytes | None,
        }
    """
    if not MODAL_ENDPOINT:
        raise RuntimeError("MODAL_ENDPOINT_URL not configured")

    image_base64 = base64.b64encode(image_bytes).decode()

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            MODAL_ENDPOINT,
            json={"image_base64": image_base64},
        )
        response.raise_for_status()
        result = response.json()

    # Decode base64 images back to bytes
    if result.get("cropped_image"):
        result["cropped_image"] = base64.b64decode(result["cropped_image"])
    if result.get("thumbnail"):
        result["thumbnail"] = base64.b64decode(result["thumbnail"])

    logger.info(f"Modal inference: is_stone={result['is_stone']}, confidence={result['confidence']:.4f}")
    return result


class ModalMLService:
    """Drop-in replacement for CLIPService using Modal backend."""

    async def process_image(self, image_bytes: bytes) -> dict:
        """Process image through Modal API."""
        return await process_image_remote(image_bytes)

    def is_stone(self, image_bytes: bytes, threshold: float = 0.05) -> tuple[bool, float]:
        """Sync wrapper - NOT RECOMMENDED, use async version."""
        import asyncio
        result = asyncio.run(process_image_remote(image_bytes))
        return result["is_stone"], result["confidence"]

    def get_embedding(self, image_bytes: bytes) -> list[float]:
        """Sync wrapper - NOT RECOMMENDED, use async version."""
        import asyncio
        result = asyncio.run(process_image_remote(image_bytes))
        return result["embedding"]

    def smart_crop_stone(self, image_bytes: bytes) -> tuple[bytes, bytes] | None:
        """Sync wrapper - NOT RECOMMENDED, use async version."""
        import asyncio
        result = asyncio.run(process_image_remote(image_bytes))
        if result["cropped_image"] and result["thumbnail"]:
            return result["cropped_image"], result["thumbnail"]
        return None


# Singleton for compatibility with existing code
_modal_service = None


def get_modal_service() -> ModalMLService:
    """Get Modal ML service instance."""
    global _modal_service
    if _modal_service is None:
        _modal_service = ModalMLService()
    return _modal_service
