# image_search.py
import os
import json
import logging
import re
import requests
from pathlib import Path
from urllib.parse import quote
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

class SimpleArtistImageSearch:
    def __init__(self):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.images_dir = os.path.join(self.base_dir, "images")
        self.artists_dir = os.path.join(self.base_dir, "artists")
        os.makedirs(self.images_dir, exist_ok=True)
        os.makedirs(self.artists_dir, exist_ok=True)

        self.pixian_api_key = os.getenv('PIXIAN_API_KEY')
        self.pixian_secret_key = os.getenv('PIXIAN_SECRET_KEY')
        self.artist_cache = {}
        self.photo_cache_file = os.path.join(self.base_dir, "artist_photo_cache.json")
        self._load_photo_cache()

    def _load_photo_cache(self):
        try:
            if os.path.exists(self.photo_cache_file):
                with open(self.photo_cache_file, 'r', encoding='utf-8') as f:
                    self.photo_cache = json.load(f)
                logger.info(f"📦 Загружен кэш фото: {len(self.photo_cache)} артистов")
            else:
                self.photo_cache = {}
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки кэша фото: {e}")
            self.photo_cache = {}

    def _save_photo_cache(self):
        try:
            with open(self.photo_cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.photo_cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения кэша фото: {e}")

    def _remove_background_pixian(self, image_path: str) -> str:
        """Удаляет фон через Pixian.ai API"""
        try:
            if not self.pixian_api_key or not self.pixian_secret_key:
                logger.warning("⚠️ Pixian API ключи не установлены, пропускаем удаление фона")
                return image_path

            with open(image_path, 'rb') as img_file:
                response = requests.post(
                    'https://api.pixian.ai/api/v2/remove-background',
                    files={'image': img_file},
                    data={
                        'format': 'png', 
                        'quality': 'high',
                        'cropping': '-1'  # Автоматическое кадрирование
                    },
                    auth=(self.pixian_api_key, self.pixian_secret_key)
                )

            if response.status_code == 200:
                output_path = image_path.replace('.jpg', '_nobg.png').replace('.jpeg', '_nobg.png')
                with open(output_path, 'wb') as out:
                    out.write(response.content)
                
                logger.info(f"✅ Фон удален через Pixian.ai: {output_path}")
                return output_path
            else:
                logger.error(f"❌ Ошибка Pixian.ai: {response.status_code} - {response.text}")
                return image_path

        except Exception as e:
            logger.error(f"❌ Ошибка удаления фона: {e}")
            return image_path

    def _search_wikipedia(self, artist_name: str) -> str:
        """Поиск фото в Wikipedia"""
        try:
            search_url = "https://en.wikipedia.org/w/api.php"
            params = {
                'action': 'query',
                'format': 'json',
                'list': 'search',
                'srsearch': f'{artist_name} musician',
                'srlimit': 1
            }
            
            response = requests.get(search_url, params=params, timeout=10)
            data = response.json()
            
            if data.get('query', {}).get('search'):
                page_title = data['query']['search'][0]['title']
                
                image_params = {
                    'action': 'query',
                    'format': 'json',
                    'titles': page_title,
                    'prop': 'pageimages',
                    'pithumbsize': 500
                }
                
                response = requests.get(search_url, params=image_params, timeout=10)
                data = response.json()
                
                pages = data.get('query', {}).get('pages', {})
                for page_id, page_data in pages.items():
                    thumbnail = page_data.get('thumbnail')
                    if thumbnail:
                        return thumbnail.get('source')
            
            return None
            
        except Exception as e:
            logger.debug(f"Wikipedia search failed: {e}")
            return None

    def _download_image(self, url: str, track_id: int) -> str:
        """Скачивает и сохраняет изображение"""
        try:
            response = requests.get(url, timeout=15, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            response.raise_for_status()
            
            output_path = os.path.join(self.images_dir, f"{track_id}_artist.jpg")
            with open(output_path, 'wb') as f:
                f.write(response.content)
            
            logger.info(f"✅ Изображение скачано: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"❌ Ошибка скачивания изображения: {e}")
            return None

    def _create_placeholder(self, artist_name: str, track_id: int) -> str:
        """Создает placeholder изображение"""
        try:
            width, height = 400, 400
            img = Image.new('RGB', (width, height), color=(73, 109, 137))
            draw = ImageDraw.Draw(img)
            
            font = None
            font_sizes = [36, 32, 28, 24]
            
            for font_size in font_sizes:
                try:
                    font = ImageFont.truetype("arial.ttf", font_size)
                    break
                except:
                    try:
                        font = ImageFont.load_default()
                        break
                    except:
                        continue
            
            text = artist_name[:20] + "..." if len(artist_name) > 20 else artist_name
            
            if font:
                bbox = draw.textbbox((0, 0), text, font=font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
                
                x = (width - text_width) / 2
                y = (height - text_height) / 2
                
                draw.text((x, y), text, fill=(255, 255, 255), font=font)
            else:
                draw.text((width//2, height//2), text, fill=(255, 255, 255), anchor="mm")
            
            output_path = os.path.join(self.images_dir, f"{track_id}_artist.png")
            img.save(output_path, "PNG")
            logger.info(f"🖼️ Создан placeholder: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания placeholder: {e}")
            output_path = os.path.join(self.images_dir, f"{track_id}_artist.txt")
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(f"Placeholder for: {artist_name}")
            return output_path

    def _find_local_artist_photo(self, artist_name: str):
        """Поиск локального фото артиста"""
        try:
            if not os.path.exists(self.artists_dir):
                return None
                
            search_names = [
                artist_name,
                artist_name.lower(),
                artist_name.upper(),
                artist_name.replace(' ', '_'),
                artist_name.replace(' ', '-'),
                self._slugify(artist_name)
            ]
            
            search_names = list(set([name for name in search_names if name]))
            extensions = ['.jpg', '.jpeg', '.png', '.webp']
            
            for name in search_names:
                for ext in extensions:
                    direct_path = os.path.join(self.artists_dir, f"{name}{ext}")
                    if os.path.exists(direct_path):
                        logger.info(f"📁 Найдено локальное фото: {direct_path}")
                        return direct_path
                    
                    pattern = f"{name}*{ext}"
                    for file_path in Path(self.artists_dir).glob(pattern):
                        if file_path.is_file():
                            logger.info(f"📁 Найдено локальное фото по паттерну: {file_path}")
                            return str(file_path)
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка поиска локального фото: {e}")
            return None

    def fetch_artist_png(self, artist_name: str, track_id: int, use_rembg: bool = True):
        """Основной метод поиска фото артиста"""
        cache_key = f"{artist_name}_{track_id}"
        if cache_key in self.artist_cache:
            return self.artist_cache[cache_key]
        
        try:
            logger.info(f"🎭 Поиск фото для: {artist_name}")
            
            # 1. Пробуем найти локальное фото
            local_photo = self._find_local_artist_photo(artist_name)
            if local_photo:
                logger.info(f"✅ Найдено локальное фото: {local_photo}")
                
                # Удаляем фон если нужно и доступен API
                if use_rembg and self.pixian_api_key and self.pixian_secret_key:
                    processed_photo = self._remove_background_pixian(local_photo)
                    if processed_photo and processed_photo != local_photo:
                        self.artist_cache[cache_key] = processed_photo
                        return processed_photo
                
                # Конвертируем в PNG если нужно
                if local_photo.lower().endswith(('.jpg', '.jpeg')):
                    try:
                        output_path = os.path.join(self.images_dir, f"{track_id}_artist.png")
                        img = Image.open(local_photo)
                        img.save(output_path, "PNG")
                        self.artist_cache[cache_key] = output_path
                        return output_path
                    except Exception as e:
                        logger.warning(f"⚠️ Ошибка конвертации: {e}")
                
                self.artist_cache[cache_key] = local_photo
                return local_photo
            
            # 2. Пробуем поиск в Wikipedia
            wiki_url = self._search_wikipedia(artist_name)
            if wiki_url:
                downloaded_path = self._download_image(wiki_url, track_id)
                if downloaded_path:
                    # Удаляем фон если нужно
                    if use_rembg and self.pixian_api_key and self.pixian_secret_key:
                        processed_path = self._remove_background_pixian(downloaded_path)
                        if processed_path and processed_path != downloaded_path:
                            self.artist_cache[cache_key] = processed_path
                            return processed_path
                    
                    self.artist_cache[cache_key] = downloaded_path
                    return downloaded_path
            
            # 3. Создаем placeholder
            placeholder_path = self._create_placeholder(artist_name, track_id)
            self.artist_cache[cache_key] = placeholder_path
            return placeholder_path
            
        except Exception as e:
            logger.error(f"❌ Критическая ошибка поиска фото: {e}")
            placeholder_path = self._create_placeholder(artist_name, track_id)
            self.artist_cache[cache_key] = placeholder_path
            return placeholder_path

    def fetch_multiple_artist_photos(self, artist_name: str, count: int = 10):
        """Поиск нескольких фото артиста"""
        logger.info(f"🎭 Поиск {count} фото для: {artist_name}")
        
        results = []
        
        # 1. Локальные фото
        local_photo = self._find_local_artist_photo(artist_name)
        if local_photo:
            results.append(f"local://{local_photo}")
        
        # 2. Wikipedia
        wiki_url = self._search_wikipedia(artist_name)
        if wiki_url:
            results.append(wiki_url)
        
        # 3. Placeholder URLs
        placeholder_urls = [
            f"https://via.placeholder.com/400x400/667eea/white?text={quote(artist_name)}+1",
            f"https://via.placeholder.com/400x400/764ba2/white?text={quote(artist_name)}+2", 
            f"https://via.placeholder.com/400x400/f093fb/white?text={quote(artist_name)}+3"
        ]
        
        results.extend(placeholder_urls[:max(0, count - len(results))])
        
        # Обновляем кэш
        artist_key = artist_name.strip().lower()
        self.photo_cache[artist_key] = results[:20]
        self._save_photo_cache()
        
        logger.info(f"✅ Найдено {len(results)} фото")
        return results[:count]

    def _process_local_photo(self, local_path: str, track_id: int):
        """Обработка локального фото"""
        try:
            import shutil
            filename = os.path.basename(local_path)
            output_path = os.path.join(self.images_dir, f"{track_id}_artist{os.path.splitext(filename)[1]}")
            
            shutil.copy2(local_path, output_path)
            
            # Удаляем фон если доступны API ключи
            if self.pixian_api_key and self.pixian_secret_key:
                processed_path = self._remove_background_pixian(output_path)
                if processed_path and processed_path != output_path:
                    return processed_path
            
            logger.info(f"✅ Локальное фото обработано: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"❌ Ошибка обработки локального фото: {e}")
            return None

    def _slugify(self, s: str) -> str:
        s = re.sub(r"[^\w\s.-]+", "", s, flags=re.UNICODE)
        s = re.sub(r"\s+", "_", s.strip(), flags=re.UNICODE)
        return s[:140].lower()

# Глобальный экземпляр
image_searcher = SimpleArtistImageSearch()