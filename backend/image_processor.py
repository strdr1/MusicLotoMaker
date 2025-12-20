# image_processor.py
import cv2
import numpy as np
import base64
from io import BytesIO
from PIL import Image, ImageDraw
import os
import logging

logger = logging.getLogger(__name__)

class ImageProcessor:
    def __init__(self):
        pass

    def apply_eraser_batch(self, image_data, erase_operations, container_size, image_transform):
        try:
            if isinstance(image_data, str):
                if image_data.startswith('data:'):
                    image_data = image_data.split(',')[1]
                image_bytes = base64.b64decode(image_data)
                image = Image.open(BytesIO(image_bytes)).convert("RGBA")
            else:
                return None

            cv_image = cv2.cvtColor(np.array(image), cv2.COLOR_RGBA2BGRA)
            mask = np.zeros((cv_image.shape[0], cv_image.shape[1]), dtype=np.uint8)

            for operation in erase_operations:
                for point in operation['points']:
                    screen_x = point['x']
                    screen_y = point['y']
                    size = point.get('size', operation.get('size', 20))
                    
                    # Преобразуем координаты экрана в координаты изображения
                    img_x = int((screen_x - image_transform['x']) / image_transform['scale'])
                    img_y = int((screen_y - image_transform['y']) / image_transform['scale'])
                    
                    if 0 <= img_x < cv_image.shape[1] and 0 <= img_y < cv_image.shape[0]:
                        cv2.circle(mask, (img_x, img_y), int(size // 2), 255, -1)

            # Применяем маску
            cv_image[mask == 255] = [0, 0, 0, 0]
            result_image = Image.fromarray(cv2.cvtColor(cv_image, cv2.COLOR_BGRA2RGBA))
            return result_image

        except Exception as e:
            logger.error(f"❌ Ошибка ластика: {e}")
            return None

    def apply_crop(self, image_data, crop_rect, container_size, image_transform):
        """Обрезка изображения"""
        try:
            if isinstance(image_data, str):
                if image_data.startswith('data:'):
                    image_data = image_data.split(',')[1]
                image_bytes = base64.b64decode(image_data)
                image = Image.open(BytesIO(image_bytes)).convert("RGBA")
            else:
                return None

            img_w, img_h = image.size

            def to_img_coords(sx, sy):
                ix = int((sx - image_transform['x']) / image_transform['scale'])
                iy = int((sy - image_transform['y']) / image_transform['scale'])
                return (
                    max(0, min(ix, img_w - 1)),
                    max(0, min(iy, img_h - 1))
                )

            # Преобразуем координаты обрезки
            x1, y1 = to_img_coords(crop_rect['x'], crop_rect['y'])
            x2, y2 = to_img_coords(crop_rect['x'] + crop_rect['width'], crop_rect['y'] + crop_rect['height'])

            # Убеждаемся, что координаты корректны
            x1, x2 = sorted([x1, x2])
            y1, y2 = sorted([y1, y2])
            
            # Минимальный размер 1x1 пиксель
            x2 = max(x1 + 1, x2)
            y2 = max(y1 + 1, y2)
            
            # Проверяем размеры
            if x2 - x1 <= 0 or y2 - y1 <= 0:
                logger.error("❌ Неверные размеры обрезки")
                return None

            cropped = image.crop((x1, y1, x2, y2))
            return cropped

        except Exception as e:
            logger.error(f"❌ Ошибка обрезки: {e}")
            return None

    def apply_selection_mask(self, image_data, selection_points, container_size, image_transform):
        """Вырезание по выделенной области"""
        try:
            if isinstance(image_data, str):
                if image_data.startswith('data:'):
                    image_data = image_data.split(',')[1]
                image_bytes = base64.b64decode(image_data)
                image = Image.open(BytesIO(image_bytes)).convert("RGBA")
            else:
                return None

            mask = Image.new('L', image.size, 0)
            draw = ImageDraw.Draw(mask)
            
            # Преобразуем точки выделения
            pts = []
            for p in selection_points:
                x = int((p['x'] - image_transform['x']) / image_transform['scale'])
                y = int((p['y'] - image_transform['y']) / image_transform['scale'])
                pts.append((x, y))
            
            # Рисуем полигон только если есть достаточно точек
            if len(pts) > 2:
                draw.polygon(pts, fill=255)
                
                # ИСПРАВЛЕННАЯ ЧАСТЬ: правильное применение маски
                # Конвертируем изображение в RGBA если нужно
                if image.mode != 'RGBA':
                    image = image.convert('RGBA')
                
                # Создаем прозрачное изображение
                result = Image.new('RGBA', image.size, (0, 0, 0, 0))
                
                # Вставляем оригинальное изображение используя маску
                result.paste(image, (0, 0), mask)
                return result
            else:
                logger.error("❌ Недостаточно точек для выделения")
                return None

        except Exception as e:
            logger.error(f"❌ Ошибка выделения: {e}")
            return None

    def image_to_base64(self, image):
        """Конвертация PIL Image в base64"""
        try:
            if image is None:
                return ""
            buf = BytesIO()
            image.save(buf, format="PNG")
            return base64.b64encode(buf.getvalue()).decode()
        except Exception as e:
            logger.error(f"❌ Ошибка конвертации в base64: {e}")
            return ""

    def save_image(self, image, path):
        """Сохранение изображения"""
        try:
            # Создаем директорию если не существует
            os.makedirs(os.path.dirname(path), exist_ok=True)
            
            if os.path.exists(path):
                os.remove(path)
            image.save(path, "PNG")
            logger.info(f"✅ Изображение сохранено: {path}")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения изображения: {e}")
            return False

image_processor = ImageProcessor()