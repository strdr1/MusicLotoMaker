# backend/image_search.py
import requests
import os
import urllib.parse
import logging
from PIL import Image, ImageDraw, ImageFont
import hashlib

logger = logging.getLogger(__name__)

class ImageSearch:
    def __init__(self):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.images_dir = os.path.join(self.base_dir, "images")
        os.makedirs(self.images_dir, exist_ok=True)
    
    def search_and_download_artist_image(self, artist_name, track_id):
        """Поиск и скачивание изображения артиста с fallback"""
        try:
            logger.info(f"🔍 Поиск фото для: {artist_name}")
            
            # Пробуем разные источники по очереди
            image_url = None
            
            # 1. Пробуем Last.fm (если есть API ключ)
            image_url = self._search_lastfm(artist_name)
            
            # 2. Пробуем MusicBrainz
            if not image_url:
                image_url = self._search_musicbrainz(artist_name)
            
            # 3. Пробуем Google через сервис (если настроен)
            if not image_url:
                image_url = self._search_google_images(artist_name)
            
            # 4. Пробуем Яндекс (если настроен)
            if not image_url:
                image_url = self._search_yandex_images(artist_name)
            
            # Если нашли URL, скачиваем
            if image_url:
                image_path = os.path.join(self.images_dir, f"{track_id}_artist.jpg")
                if self._download_image(image_url, image_path):
                    logger.info(f"✅ Фото скачано: {image_path}")
                    return image_path
            
            # Если не нашли, создаем placeholder
            logger.info(f"🔄 Создаем placeholder для: {artist_name}")
            return self._create_placeholder_image(artist_name, track_id)
            
        except Exception as e:
            logger.error(f"❌ Ошибка поиска изображения: {e}")
            return self._create_placeholder_image(artist_name, track_id)
    
    def _search_lastfm(self, artist_name):
        """Поиск через Last.fm API"""
        try:
            api_key = os.getenv('LASTFM_API_KEY')
            if not api_key:
                return None
                
            url = f"http://ws.audioscrobbler.com/2.0/?method=artist.getinfo&artist={artist_name}&api_key={api_key}&format=json"
            
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                images = data.get('artist', {}).get('image', [])
                
                # Ищем изображение большого размера
                for image in images:
                    if image.get('size') == 'extralarge':
                        image_url = image.get('#text')
                        if image_url and image_url.strip():
                            logger.info(f"✅ Найдено в Last.fm: {image_url}")
                            return image_url
            return None
            
        except Exception as e:
            logger.warning(f"⚠️ Last.fm search error: {e}")
            return None
    
    def _search_musicbrainz(self, artist_name):
        """Поиск через MusicBrainz API"""
        try:
            # MusicBrainz требует сложной интеграции с обложками
            # Пока возвращаем None - можно доработать позже
            return None
            
        except Exception as e:
            logger.warning(f"⚠️ MusicBrainz search error: {e}")
            return None
    
    def _search_google_images(self, artist_name):
        """Поиск через Google Images API"""
        try:
            api_key = os.getenv('GOOGLE_API_KEY')
            search_engine_id = os.getenv('GOOGLE_SEARCH_ENGINE_ID')
            
            if not api_key or not search_engine_id:
                return None
                
            search_query = f"{artist_name} musician artist"
            url = f"https://www.googleapis.com/customsearch/v1?q={search_query}&key={api_key}&cx={search_engine_id}&searchType=image"
            
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                items = data.get('items', [])
                if items:
                    image_url = items[0].get('link')
                    logger.info(f"✅ Найдено в Google: {image_url}")
                    return image_url
            return None
            
        except Exception as e:
            logger.warning(f"⚠️ Google Images search error: {e}")
            return None
    
    def _search_yandex_images(self, artist_name):
        """Поиск через Яндекс.Картинки"""
        try:
            # Яндекс требует OAuth и сложной настройки
            return None
            
        except Exception as e:
            logger.warning(f"⚠️ Yandex Images search error: {e}")
            return None
    
    def _download_image(self, image_url, save_path):
        """Скачивает изображение"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            response = requests.get(image_url, timeout=15, headers=headers)
            if response.status_code == 200:
                with open(save_path, 'wb') as f:
                    f.write(response.content)
                
                # Проверяем что файл валидный
                try:
                    with Image.open(save_path) as img:
                        img.verify()
                    return True
                except Exception:
                    logger.warning(f"⚠️ Невалидное изображение: {image_url}")
                    os.remove(save_path)
                    return False
            else:
                logger.warning(f"⚠️ Не удалось скачать: {image_url} - статус {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки изображения: {e}")
            return False
    
    def _create_placeholder_image(self, artist_name, track_id):
        """Создает красивое placeholder изображение"""
        try:
            # Создаем изображение с градиентом
            width, height = 400, 400
            image = Image.new('RGB', (width, height), color=(41, 128, 185))
            draw = ImageDraw.Draw(image)
            
            # Добавляем градиентный эффект
            for i in range(height):
                r = int(41 + (100 * i / height))
                g = int(128 + (50 * i / height))
                b = int(185 - (50 * i / height))
                draw.line([(0, i), (width, i)], fill=(r, g, b))
            
            # Пробуем использовать разные шрифты
            font_size = 32
            font = None
            
            # Список возможных шрифтов
            font_paths = [
                "arial.ttf",
                "Arial.ttf", 
                "/System/Library/Fonts/Arial.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
            ]
            
            for font_path in font_paths:
                try:
                    font = ImageFont.truetype(font_path, font_size)
                    break
                except:
                    continue
            
            if font is None:
                # Используем стандартный шрифт
                font = ImageFont.load_default()
            
            # Подготавливаем текст
            text = artist_name.upper()
            if len(text) > 20:
                text = text[:17] + "..."
            
            # Получаем размеры текста
            try:
                bbox = draw.textbbox((0, 0), text, font=font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
            except:
                # Fallback для старых версий PIL
                text_width = len(text) * font_size * 0.6
                text_height = font_size
            
            # Позиционируем текст по центру
            x = (width - text_width) / 2
            y = (height - text_height) / 2
            
            # Добавляем тень текста
            shadow_color = (25, 25, 25)
            draw.text((x+2, y+2), text, fill=shadow_color, font=font)
            
            # Основной текст
            text_color = (255, 255, 255)
            draw.text((x, y), text, fill=text_color, font=font)
            
            # Добавляем иконку ноты
            try:
                # Простая нота символами
                note_symbol = "♫"
                note_font_size = 80
                note_font = ImageFont.truetype(font_paths[0], note_font_size) if font_paths else font
                note_bbox = draw.textbbox((0, 0), note_symbol, font=note_font)
                note_width = note_bbox[2] - note_bbox[0]
                note_x = (width - note_width) / 2
                note_y = y - 100
                draw.text((note_x, note_y), note_symbol, fill=(255, 255, 255, 180), font=note_font)
            except:
                pass
            
            # Сохраняем
            image_path = os.path.join(self.images_dir, f"{track_id}_artist.jpg")
            image.save(image_path, "JPEG", quality=85)
            
            logger.info(f"✅ Создан placeholder: {image_path}")
            return image_path
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания placeholder: {e}")
            return None

# Глобальный экземпляр
image_searcher = ImageSearch()