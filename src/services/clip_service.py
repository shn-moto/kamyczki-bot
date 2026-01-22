import logging
import torch
import open_clip
from PIL import Image, ImageFilter
from io import BytesIO
import numpy as np

logger = logging.getLogger(__name__)

class CLIPService:
    def __init__(self):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        # ViT-B-32 ожидает вход 224x224. Мы будем подавать качественный кроп.
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(
            "ViT-B-32", pretrained="laion2b_s34b_b79k"
        )
        self.model = self.model.to(self.device)
        self.model.eval()
        self.tokenizer = open_clip.get_tokenizer("ViT-B-32")

        # Промпты для детекции камня
        self.stone_prompts = [
            "a painted stone with artwork",
            "a decorated rock with drawing",
            "a stone with painted picture",
            "hand painted pebble art",
            "rock painting craft",
            "decorated stone with art",
            "painted rock with flowers",
        ]
        self.not_stone_prompts = [
            "a photograph of a person",
            "a screenshot of text",
            "a blank white image",
            "a room interior",
        ]

        # Предварительный расчет эмбеддингов для классификации
        with torch.no_grad():
            stone_tokens = self.tokenizer(self.stone_prompts).to(self.device)
            not_stone_tokens = self.tokenizer(self.not_stone_prompts).to(self.device)
            self.stone_text_features = self.model.encode_text(stone_tokens)
            self.not_stone_text_features = self.model.encode_text(not_stone_tokens)
            self.stone_text_features /= self.stone_text_features.norm(dim=-1, keepdim=True)
            self.not_stone_text_features /= self.not_stone_text_features.norm(dim=-1, keepdim=True)

    def is_stone(self, image_bytes: bytes, threshold: float = 0.05) -> tuple[bool, float]:
        """Проверка, содержит ли изображение раскрашенный камень."""
        image = Image.open(BytesIO(image_bytes)).convert("RGB")
        image_input = self.preprocess(image).unsqueeze(0).to(self.device)

        with torch.no_grad():
            image_features = self.model.encode_image(image_input)
            image_features /= image_features.norm(dim=-1, keepdim=True)

            stone_similarity = (image_features @ self.stone_text_features.T).mean().item()
            not_stone_similarity = (image_features @ self.not_stone_text_features.T).mean().item()

        score = stone_similarity - not_stone_similarity
        logger.info(f"Stone detection: stone_sim={stone_similarity:.4f}, not_stone_sim={not_stone_similarity:.4f}, score={score:.4f}")
        return score > threshold, score

    def get_embedding(self, image_bytes: bytes) -> list[float]:
        """Получение CLIP эмбеддинга для изображения (512 измерений)."""
        image = Image.open(BytesIO(image_bytes)).convert("RGB")
        image_input = self.preprocess(image).unsqueeze(0).to(self.device)

        with torch.no_grad():
            image_features = self.model.encode_image(image_input)
            image_features /= image_features.norm(dim=-1, keepdim=True)

        return image_features.cpu().numpy().flatten().tolist()

    def encode_text_query(self, text: str) -> list[float]:
        """Кодирование текстового запроса для семантического поиска."""
        tokens = self.tokenizer([text]).to(self.device)
        with torch.no_grad():
            text_features = self.model.encode_text(tokens)
            text_features /= text_features.norm(dim=-1, keepdim=True)
        return text_features.cpu().numpy().flatten().tolist()

    def smart_crop_stone(self, image_bytes: bytes) -> tuple[bytes, bytes] | None:
        """
        Улучшенный умный кроп с фильтром резкости и повышенным разрешением.
        """
        from rembg import remove
        from PIL import ImageFilter # Добавьте этот импорт в начало файла!

        # Удаление фона
        image_rgba = Image.open(BytesIO(image_bytes)).convert("RGBA")
        result_rgba = remove(image_rgba)

        bbox = result_rgba.getbbox()
        if not bbox:
            logger.warning("smart_crop_stone: объект не найден")
            return None

        # Адаптивный padding
        x1, y1, x2, y2 = bbox
        obj_w, obj_h = x2 - x1, y2 - y1
        padding = int(max(obj_w, obj_h) * 0.1)

        x1 = max(0, x1 - padding)
        y1 = max(0, y1 - padding)
        x2 = min(result_rgba.width, x2 + padding)
        y2 = min(result_rgba.height, y2 + padding)

        # Кропим оригинал
        original_rgb = Image.open(BytesIO(image_bytes)).convert("RGB")
        cropped_image = original_rgb.crop((x1, y1, x2, y2))

        # 1. КРОП ДЛЯ ML (PNG без потерь)
        ml_output = BytesIO()
        cropped_image.save(ml_output, format="PNG")
        cropped_bytes = ml_output.getvalue()

        # 2. МИНИАТЮРА ДЛЯ ПОЛЬЗОВАТЕЛЯ (600x600 + Sharpness)
        thumb_image = cropped_image.copy()
        # Используем современный синтаксис Resampling
        thumb_image.thumbnail((600, 600), Image.Resampling.LANCZOS)
        
        # Повышаем резкость, чтобы убрать эффект "мыла"
        thumb_image = thumb_image.filter(ImageFilter.UnsharpMask(radius=1, percent=150, threshold=3))
        
        thumb_output = BytesIO()
        # Сохраняем с максимальным качеством для превью
        thumb_image.save(
            thumb_output, 
            format="JPEG", 
            quality=95, 
            subsampling=0, 
            optimize=True
        )
        thumbnail_bytes = thumb_output.getvalue()

        logger.info(f"Smart crop complete: ML_size={len(cropped_bytes)}, Thumb_size={len(thumbnail_bytes)}")
        return cropped_bytes, thumbnail_bytes

    def crop_to_center(self, image_bytes: bytes, ratio: float = 0.7) -> bytes:
        """Простой кроп центральной области (если rembg не используется)."""
        image = Image.open(BytesIO(image_bytes)).convert("RGB")
        width, height = image.size

        new_width = int(width * ratio)
        new_height = int(height * ratio)
        left = (width - new_width) // 2
        top = (height - new_height) // 2

        cropped = image.crop((left, top, left + new_width, top + new_height))

        output = BytesIO()
        cropped.save(output, format="JPEG", quality=90)
        return output.getvalue()

# Singleton
_clip_service = None

def get_clip_service() -> CLIPService:
    global _clip_service
    if _clip_service is None:
        _clip_service = CLIPService()
    return _clip_service