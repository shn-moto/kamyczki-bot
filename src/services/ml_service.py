"""Unified ML service - switches between local CLIP and Modal serverless."""

import logging
from src.config import settings

logger = logging.getLogger(__name__)


async def process_image(image_bytes: bytes) -> dict:
    """Process image using configured ML backend.

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
    if settings.use_local_ml:
        return await _process_local(image_bytes)
    else:
        return await _process_modal(image_bytes)


async def _process_local(image_bytes: bytes) -> dict:
    """Process using local CLIP + rembg."""
    from src.services.clip_service import get_clip_service

    clip = get_clip_service()

    # Smart crop
    crop_result = clip.smart_crop_stone(image_bytes)
    if not crop_result:
        return {
            "is_stone": False,
            "confidence": 0.0,
            "embedding": None,
            "cropped_image": None,
            "thumbnail": None,
        }

    cropped_bytes, thumbnail_bytes = crop_result

    # Stone detection
    is_stone, confidence = clip.is_stone(cropped_bytes)

    if not is_stone:
        return {
            "is_stone": False,
            "confidence": confidence,
            "embedding": None,
            "cropped_image": cropped_bytes,
            "thumbnail": thumbnail_bytes,
        }

    # Get embedding
    embedding = clip.get_embedding(cropped_bytes)

    return {
        "is_stone": True,
        "confidence": confidence,
        "embedding": embedding,
        "cropped_image": cropped_bytes,
        "thumbnail": thumbnail_bytes,
    }


async def _process_modal(image_bytes: bytes) -> dict:
    """Process using Modal serverless API."""
    from src.services.modal_client import process_image_remote

    return await process_image_remote(image_bytes)


def preload_models():
    """Pre-load models at startup (only for local mode)."""
    if settings.use_local_ml:
        logger.info("Loading local ML models...")
        from src.services.clip_service import get_clip_service
        from rembg import new_session

        get_clip_service()
        new_session("u2net")
        logger.info("Local ML models loaded")
    else:
        logger.info("Using Modal serverless ML - no local models to load")
