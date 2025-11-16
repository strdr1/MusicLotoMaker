import cv2
import numpy as np
import base64
from io import BytesIO
from PIL import Image, ImageDraw
import os
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ImageProcessor:
    def __init__(self):
        pass
    
    def apply_eraser_batch(self, image_data, erase_operations, container_size, image_transform):
        """Применяет ВСЕ операции ластика за один раз"""
        try:
            if isinstance(image_data, str):
                if ',' in image_data:
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
                    
                    img_x = int((screen_x - image_transform['x']) / image_transform['scale'])
                    img_y = int((screen_y - image_transform['y']) / image_transform['scale'])
                    
                    if (0 <= img_x < cv_image.shape[1] and 
                        0 <= img_y < cv_image.shape[0]):
                        cv2.circle(mask, (img_x, img_y), size // 2, 255, -1)
            
            cv_image[mask == 255] = [0, 0, 0, 0]
            result_image = Image.fromarray(cv2.cvtColor(cv_image, cv2.COLOR_BGRA2RGBA))
            return result_image
            
        except Exception as e:
            logger.error(f"❌ Ошибка применения ластика: {e}")
            return None
    
    def apply_crop(self, image_data, crop_rect, original_size, container_size):
        """Обрезает изображение"""
        try:
            if isinstance(image_data, str):
                if ',' in image_data:
                    image_data = image_data.split(',')[1]
                image_bytes = base64.b64decode(image_data)
                image = Image.open(BytesIO(image_bytes))
            else:
                image = image_data
            
            img_width, img_height = image.size
            
            scale_x = img_width / original_size['width']
            scale_y = img_height / original_size['height']
            
            x1 = int((crop_rect['x']) * scale_x)
            y1 = int((crop_rect['y']) * scale_y)
            x2 = int((crop_rect['x'] + crop_rect['width']) * scale_x)
            y2 = int((crop_rect['y'] + crop_rect['height']) * scale_y)
            
            x1 = max(0, min(x1, img_width - 1))
            y1 = max(0, min(y1, img_height - 1))
            x2 = max(x1 + 1, min(x2, img_width))
            y2 = max(y1 + 1, min(y2, img_height))
            
            cropped = image.crop((x1, y1, x2, y2))
            return cropped
            
        except Exception as e:
            logger.error(f"❌ Ошибка обрезки: {e}")
            return None
    
    def apply_selection_mask(self, image_data, selection_points, container_size, image_transform):
        """Вырезает по выделенной области"""
        try:
            if isinstance(image_data, str):
                if ',' in image_data:
                    image_data = image_data.split(',')[1]
                
                image_bytes = base64.b64decode(image_data)
                image = Image.open(BytesIO(image_bytes)).convert("RGBA")
            else:
                return None
            
            # Создаем маску на основе выделенной области
            mask = Image.new('L', image.size, 0)
            draw = ImageDraw.Draw(mask)
            
            # Преобразуем точки выделения в координаты изображения
            polygon_points = []
            for point in selection_points:
                img_x = int((point['x'] - image_transform['x']) / image_transform['scale'])
                img_y = int((point['y'] - image_transform['y']) / image_transform['scale'])
                polygon_points.append((img_x, img_y))
            
            # Рисуем заполненный полигон
            if len(polygon_points) > 2:
                draw.polygon(polygon_points, fill=255)
            
            # Применяем маску
            result = Image.new('RGBA', image.size, (0, 0, 0, 0))
            result.paste(image, (0, 0), mask)
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Ошибка вырезки по выделению: {e}")
            return None
    
    def image_to_base64(self, image):
        """Конвертирует PIL Image в base64"""
        try:
            buffered = BytesIO()
            image.save(buffered, format="PNG")
            return base64.b64encode(buffered.getvalue()).decode()
        except Exception as e:
            logger.error(f"❌ Ошибка конвертации в base64: {e}")
            return ""
    
    def save_image(self, image, filepath):
        """Сохраняет изображение с перезаписью существующего"""
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
            
            image.save(filepath, "PNG")
            logger.info(f"✅ Изображение сохранено: {filepath}")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения изображения: {e}")
            return False

# Создаем глобальный экземпляр
image_processor = ImageProcessor()