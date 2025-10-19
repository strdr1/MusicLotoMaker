import requests
import os
import logging
from PIL import Image, ImageDraw, ImageFont
from rembg import remove
from dotenv import load_dotenv
from bs4 import BeautifulSoup
import re

load_dotenv()
logger = logging.getLogger(__name__)

class SimpleArtistImageSearch:
    def __init__(self):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.images_dir = os.path.join(self.base_dir, "images")
        os.makedirs(self.images_dir, exist_ok=True)
        
        self.artist_cache = {}

    def fetch_artist_png(self, artist_name, track_id, use_rembg=True):
        """Упрощенный поиск фото артистов"""
        
        cache_key = f"{artist_name}_{track_id}"
        if cache_key in self.artist_cache:
            return self.artist_cache[cache_key]
            
        try:
            logger.info(f"🎭 Поиск фото для: {artist_name}")
            
            # Сначала Яндекс
            image_urls = self._search_yandex_simple(artist_name)
            logger.info(f"🔍 Яндекс нашёл {len(image_urls)} URL")
            
            # Если нет результатов, пробуем Google
            if not image_urls:
                logger.info("🔄 Яндекс не дал результатов, пробуем Google")
                image_urls = self._search_google_simple(artist_name)
                logger.info(f"🔍 Google нашёл {len(image_urls)} URL")
            
            final_path = os.path.join(self.images_dir, f"{track_id}_artist.png")
            
            # Пробуем скачать и обработать каждое изображение
            for idx, image_url in enumerate(image_urls):
                logger.info(f"📥 Попытка #{idx+1}: {image_url}")
                
                if self._download_and_save_image(image_url, final_path, use_rembg):
                    logger.info(f"✅ Успешно сохранено: {final_path}")
                    self.artist_cache[cache_key] = final_path
                    return final_path
            
            # Если ничего не нашлось, создаем placeholder
            logger.warning("❌ Не удалось найти ни одного изображения")
            final_path = self._create_placeholder_image(artist_name, track_id)
            self.artist_cache[cache_key] = final_path
            return final_path
            
        except Exception as e:
            logger.error(f"💥 Критическая ошибка: {e}")
            return self._create_placeholder_image(artist_name, track_id)

    def _search_yandex_simple(self, artist_name):
        """Простой поиск в Яндекс Картинках"""
        try:
            query = f"{artist_name} фото".replace(" ", "+")
            url = f"https://yandex.ru/images/search?text={query}"
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
            }
            
            logger.info(f"🌐 Запрос к Яндекс: {url}")
            response = requests.get(url, headers=headers, timeout=15)
            
            if response.status_code != 200:
                logger.warning(f"⚠️ Яндекс вернул статус {response.status_code}")
                return []
            
            soup = BeautifulSoup(response.text, 'html.parser')
            image_urls = []
            
            # Ищем все img теги
            for img in soup.find_all('img'):
                src = img.get('src') or img.get('data-src')
                if src:
                    # Преобразуем относительные URL в абсолютные
                    if src.startswith('//'):
                        full_url = 'https:' + src
                    elif src.startswith('/'):
                        full_url = 'https://yandex.ru' + src
                    else:
                        full_url = src
                    
                    # Проверяем что это изображение
                    if any(ext in full_url.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp']):
                        # Исключаем иконки и маленькие изображения
                        if not any(bad in full_url.lower() for bad in ['icon', 'logo', 'favicon', 'button']):
                            image_urls.append(full_url)
                            logger.info(f"📷 Найдено изображение: {full_url[:80]}...")
                
                if len(image_urls) >= 10:  # Ограничиваем количество
                    break
            
            return image_urls
            
        except Exception as e:
            logger.error(f"❌ Ошибка Яндекс поиска: {e}")
            return []

    def _search_google_simple(self, artist_name):
        """Простой поиск в Google"""
        try:
            api_key = os.getenv('GOOGLE_API_KEY')
            search_engine_id = os.getenv('GOOGLE_SEARCH_ENGINE_ID')
            
            if not api_key or not search_engine_id:
                logger.warning("⚠️ Отсутствуют ключи Google API")
                return []
            
            query = f"{artist_name} photo".replace(" ", "+")
            url = f"https://www.googleapis.com/customsearch/v1"
            params = {
                'q': query,
                'key': api_key,
                'cx': search_engine_id,
                'searchType': 'image',
                'num': 5
            }
            
            logger.info(f"🌐 Запрос к Google: {query}")
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                items = data.get('items', [])
                
                image_urls = []
                for item in items:
                    link = item.get('link', '')
                    if link and any(ext in link.lower() for ext in ['.jpg', '.jpeg', '.png']):
                        image_urls.append(link)
                        logger.info(f"📷 Google изображение: {link[:80]}...")
                
                return image_urls
            else:
                logger.warning(f"⚠️ Google API ошибка: {response.status_code}")
                return []
                
        except Exception as e:
            logger.error(f"❌ Ошибка Google поиска: {e}")
            return []

    def _download_and_save_image(self, image_url, final_path, use_rembg):
        """Скачивает и сохраняет изображение"""
        temp_path = final_path.replace('.png', '_temp.jpg')
        
        try:
            logger.info(f"⬇️ Скачиваем: {image_url[:100]}...")
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.get(image_url, headers=headers, timeout=15)
            if response.status_code != 200:
                logger.warning(f"⚠️ Ошибка загрузки: статус {response.status_code}")
                return False
            
            # Сохраняем временный файл
            with open(temp_path, 'wb') as f:
                f.write(response.content)
            
            logger.info(f"💾 Временный файл сохранён: {temp_path}")
            
            # Проверяем что файл не пустой
            file_size = os.path.getsize(temp_path)
            if file_size == 0:
                logger.warning("⚠️ Файл пустой")
                os.remove(temp_path)
                return False
            
            # Пробуем открыть изображение
            try:
                with Image.open(temp_path) as img:
                    # Проверяем базовые параметры
                    width, height = img.size
                    logger.info(f"📐 Размер изображения: {width}x{height}")
                    
                    if width < 100 or height < 100:
                        logger.warning("⚠️ Слишком маленькое изображение")
                        os.remove(temp_path)
                        return False
                        
            except Exception as e:
                logger.warning(f"⚠️ Невалидное изображение: {e}")
                os.remove(temp_path)
                return False
            
            # Обрабатываем изображение
            if use_rembg:
                try:
                    logger.info("🎨 Удаляем фон...")
                    with open(temp_path, 'rb') as i:
                        input_data = i.read()
                    output_data = remove(input_data)
                    with open(final_path, 'wb') as o:
                        o.write(output_data)
                    logger.info(f"✅ Фон удалён, сохранено: {final_path}")
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка удаления фона: {e}")
                    # Если не удалось удалить фон, просто конвертируем в PNG
                    with Image.open(temp_path) as img:
                        img.save(final_path, "PNG")
                    logger.info(f"✅ Просто конвертировано в PNG: {final_path}")
            else:
                # Просто конвертируем в PNG
                with Image.open(temp_path) as img:
                    img.save(final_path, "PNG")
                logger.info(f"✅ Конвертировано в PNG: {final_path}")
            
            # Удаляем временный файл
            if os.path.exists(temp_path):
                os.remove(temp_path)
            
            # Проверяем что финальный файл создан и не пустой
            if os.path.exists(final_path) and os.path.getsize(final_path) > 0:
                logger.info(f"✅ Файл успешно создан: {final_path} ({os.path.getsize(final_path)} bytes)")
                return True
            else:
                logger.warning("❌ Финальный файл не создан или пустой")
                return False
                
        except Exception as e:
            logger.error(f"💥 Ошибка при обработке изображения: {e}")
            # Очищаем временные файлы
            if os.path.exists(temp_path):
                os.remove(temp_path)
            if os.path.exists(final_path):
                os.remove(final_path)
            return False

    def _create_placeholder_image(self, artist_name, track_id):
        """Создает простой placeholder"""
        try:
            width, height = 400, 400
            image = Image.new('RGB', (width, height), color=(74, 107, 156))
            draw = ImageDraw.Draw(image)
            
            # Простой текст
            font = self._get_best_font(24)
            text = artist_name
            
            if len(text) > 20:
                text = text[:17] + "..."
            
            try:
                bbox = draw.textbbox((0, 0), text, font=font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
                x = (width - text_width) / 2
                y = (height - text_height) / 2
            except:
                x = 50
                y = 180
            
            draw.text((x, y), text, fill=(255, 255, 255), font=font)
            
            image_path = os.path.join(self.images_dir, f"{track_id}_artist.png")
            image.save(image_path, "PNG")
            
            logger.info(f"🖼️ Создан placeholder: {image_path}")
            return image_path
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания placeholder: {e}")
            return None

    def _get_best_font(self, size):
        """Находит шрифт"""
        font_paths = [
            "arial.ttf", "Arial.ttf",
            "/System/Library/Fonts/Arial.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        ]
        
        for font_path in font_paths:
            try:
                return ImageFont.truetype(font_path, size)
            except:
                continue
        
        return ImageFont.load_default()

# Глобальный экземпляр
image_searcher = SimpleArtistImageSearch()