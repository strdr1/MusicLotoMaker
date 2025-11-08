# -*- coding: utf-8 -*-
import os, io, re, json, logging, requests
from pathlib import Path
from typing import List, Optional
from PIL import Image, ImageOps, ImageFile, ImageDraw, ImageFont
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)
ImageFile.LOAD_TRUNCATED_IMAGES = True

# ----------------- Константы/настройки -----------------
MIN_W, MIN_H = 512, 512
ASPECT_MIN, ASPECT_MAX = 0.75, 1.8
TIMEOUT = 15

# ----------------- Улучшенный Rembg -----------------
_REMBG_AVAILABLE = None
_REMBG_FUNCTION = None

def _ensure_rembg():
    global _REMBG_AVAILABLE, _REMBG_FUNCTION
    if _REMBG_AVAILABLE is None:
        try:
            from rembg import remove
            _REMBG_FUNCTION = remove
            _REMBG_AVAILABLE = True
            logger.info("✅ Rembg загружен (u2netp модель)")
        except ImportError:
            _REMBG_AVAILABLE = False
            logger.warning("❌ Rembg не установлен")
    return _REMBG_AVAILABLE

def smart_remove_background(image_bytes: bytes) -> bytes:
    """Умное удаление фона с проверкой результата"""
    if not _ensure_rembg():
        raise ValueError("Rembg не установлен")
    
    try:
        output_bytes = _REMBG_FUNCTION(image_bytes, model="u2netp")
        
        img = Image.open(io.BytesIO(output_bytes))
        if img.mode == 'RGBA':
            alpha = img.getchannel('A')
            alpha_data = list(alpha.getdata())
            transparent_pixels = sum(1 for a in alpha_data if a < 10)
            total_pixels = len(alpha_data)
            
            if transparent_pixels > total_pixels * 0.8:
                logger.warning("⚠️ Rembg вырезал слишком много, используем оригинал")
                original_img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
                bg = Image.new("RGB", original_img.size, (255, 255, 255))
                bg.paste(original_img, (0, 0))
                buf = io.BytesIO()
                bg.save(buf, format="PNG")
                return buf.getvalue()
        
        return output_bytes
    except Exception as e:
        raise RuntimeError(f"Rembg error: {e}")

# ----------------- Утилиты -----------------
def ok_aspect(w: int, h: int) -> bool:
    if w <= 0 or h <= 0: return False
    r = h / float(w)
    return ASPECT_MIN <= r <= ASPECT_MAX

def download_bytes(url: str) -> Optional[bytes]:
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=TIMEOUT, stream=True)
        r.raise_for_status()
        return r.content
    except Exception as e:
        logger.debug(f"download fail: {e}")
        return None

def normalize_img(img: Image.Image, min_side: int = 900) -> Image.Image:
    img = ImageOps.exif_transpose(img.convert("RGBA"))
    w, h = img.size
    scale = max(1.0, min_side / float(min(w, h)))
    if scale > 1.01:
        img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
    return img

# ----------------- Основной класс -----------------
class SimpleArtistImageSearch:
    def __init__(self):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.images_dir = os.path.join(self.base_dir, "images")
        self.artists_dir = os.path.join(self.base_dir, "artists")
        os.makedirs(self.images_dir, exist_ok=True)
        os.makedirs(self.artists_dir, exist_ok=True)

        self.artist_cache = {}
        self.photo_cache_file = os.path.join(self.base_dir, "artist_photo_cache.json")
        self._load_photo_cache()
        
        self.use_rembg = True

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

    def _clean_name(self, s: str) -> str:
        """
        Удаляет ТОЛЬКО мешающие символы, сохраняя регистр и пробелы.
        Удаляются: ! " № ; % : ? * ( ) _ - + = @ # $ ^ & \ /
        """
        bad_chars = '!\"№;%:?*()_-+=@#$%^&\\/'
        for ch in bad_chars:
            s = s.replace(ch, '')
        s = re.sub(r'\s+', ' ', s).strip()
        return s

    def _find_local_artist_photo(self, artist_name: str) -> Optional[str]:
        """Точный поиск локального фото. Регистр НЕ учитывается."""
        if not os.path.exists(self.artists_dir):
            return None

        logger.info(f"🔍 Поиск локального фото для: '{artist_name}'")
        supported_ext = {'.jpg', '.jpeg', '.png', '.webp'}
        
        # Приводим к нижнему регистру для сравнения
        query_clean = self._clean_name(artist_name).lower()

        for f in Path(self.artists_dir).iterdir():
            if f.suffix.lower() not in supported_ext:
                continue
            # Сравниваем в нижнем регистре
            if self._clean_name(f.stem).lower() == query_clean:
                logger.info(f"✅ Найден локальный файл: {f}")
                return str(f)
        return None

    def _search_yandex_music_smart(self, artist_name: str) -> Optional[str]:
        """Поиск в Яндекс.Музыке"""
        try:
            from yandex_music import Client as YandexClient
            
            YANDEX_MUSIC_TOKEN = "y0__xC-3q2iAxje-AYglImpghUw9pW0kAgCx0SZ5vnWcYWpiGpLqwVPsGWEfg"
                
            client = YandexClient(YANDEX_MUSIC_TOKEN).init()
            search_result = client.search(artist_name)
            
            if not search_result or not search_result.artists:
                logger.info(f"🔍 Яндекс.Музыка: артист '{artist_name}' не найден")
                return None
                
            artist = search_result.artists.results[0]
            
            if hasattr(artist, 'cover') and artist.cover:
                cover_uri = getattr(artist.cover, 'uri', None)
                if cover_uri:
                    photo_url = f"https://{cover_uri.replace('%%', '1000x1000')}"
                    return photo_url
            
            if hasattr(artist, 'og_image') and artist.og_image:
                og_image_url = artist.og_image.replace('%%', '1000x1000')
                return og_image_url
            
            return None
            
        except Exception as e:
            logger.warning(f"⚠️ Ошибка поиска в Яндекс.Музыке: {e}")
            return None

    def _process_internet_photo(self, image_data: bytes, track_id: int) -> Optional[str]:
        """Обработка ТОЛЬКО интернет-фото (с проверками и rembg)"""
        try:
            img = Image.open(io.BytesIO(image_data))
            w, h = img.size
            
            if w < MIN_W or h < MIN_H or not ok_aspect(w, h): 
                logger.warning(f"⚠️ Плохое интернет-изображение: {w}x{h}")
                return None
            
            img = normalize_img(img, min_side=1024)
            out_path = Path(self.images_dir) / f"{track_id}_artist.png"

            if self.use_rembg and _ensure_rembg():
                try:
                    png_bytes = smart_remove_background(image_data)
                    with open(out_path, "wb") as f:
                        f.write(png_bytes)
                    logger.info(f"✅ Фото из интернета обработано (удаление фона): {out_path}")
                    return str(out_path)
                except Exception as e:
                    logger.warning(f"⚠️ Удаление фона не удалось: {e}")

            img.save(out_path, "PNG", optimize=True)
            logger.info(f"✅ Фото из интернета сохранено: {out_path}")
            return str(out_path)
                
        except Exception as e:
            logger.error(f"❌ Ошибка обработки интернет-фото: {e}")
            return None

    def _use_local_photo_as_is(self, local_path: str, track_id: int) -> str:
        """Используем локальный файл КАК ЕСТЬ — без изменений!"""
        try:
            out_path = Path(self.images_dir) / f"{track_id}_artist.png"
            
            # Открываем и сохраняем как PNG для единообразия
            img = Image.open(local_path)
            # Сохраняем прозрачность, если есть
            if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                img = img.convert("RGBA")
            else:
                img = img.convert("RGB")
            img.save(out_path, "PNG")
            
            logger.info(f"✅ Локальный файл использован как есть: {out_path}")
            return str(out_path)
        except Exception as e:
            logger.error(f"❌ Ошибка копирования локального файла: {e}")
            return self._create_placeholder_image("?", track_id)

    def fetch_artist_png(self, artist_name: str, track_id: int, use_rembg: bool = True):
        """Умный поиск фото с абсолютным приоритетом локальных файлов"""
        original_rembg_setting = self.use_rembg
        self.use_rembg = use_rembg
        
        try:
            # Используем нижний регистр для кэширования
            cache_key = f"{artist_name.lower()}_{track_id}_{use_rembg}"
            if cache_key in self.artist_cache:
                return self.artist_cache[cache_key]
            
            logger.info(f"🎭 Поиск фото для: '{artist_name}' (ID: {track_id})")
            
            # 🔑 АБСОЛЮТНЫЙ ПРИОРИТЕТ: локальный файл
            local_photo = self._find_local_artist_photo(artist_name)
            if local_photo:
                logger.info(f"📁 ЛОКАЛЬНЫЙ ФАЙЛ НАЙДЕН — ИСПОЛЬЗУЕТСЯ БЕЗ ПРОВЕРОК!")
                processed_path = self._use_local_photo_as_is(local_photo, track_id)
                self.artist_cache[cache_key] = processed_path
                self._cache_push(artist_name.strip().lower(), f"local://{local_photo}")
                return processed_path

            # Интернет — только если локального нет
            logger.info(f"🔍 Локальный файл НЕ найден, ищем в Яндекс.Музыке...")
            url = self._search_yandex_music_smart(artist_name)
            if url:
                image_data = download_bytes(url)
                if image_data:
                    processed_path = self._process_internet_photo(image_data, track_id)
                    if processed_path:
                        self._cache_push(artist_name.strip().lower(), url)
                        self.artist_cache[cache_key] = processed_path
                        logger.info(f"✅ Найдено в Яндекс.Музыке: {url}")
                        return processed_path

            # Placeholder
            p = self._create_placeholder_image(artist_name, track_id)
            self.artist_cache[cache_key] = p
            return p
            
        except Exception as e:
            logger.error(f"💥 Критическая ошибка: {e}")
            p = self._create_placeholder_image(artist_name, track_id)
            self.artist_cache[cache_key] = p
            return p
        finally:
            self.use_rembg = original_rembg_setting

    def _create_placeholder_image(self, artist_name: str, track_id: int) -> str:
        try:
            w, h = 600, 600
            img = Image.new("RGB", (w, h), (60, 75, 115))
            draw = ImageDraw.Draw(img)
            
            for i in range(h):
                r = max(40, min(60, 40 + i//20))
                g = max(55, min(75, 55 + i//25)) 
                b = max(95, min(115, 95 + i//15))
                draw.line([(0, i), (w, i)], fill=(r, g, b))
            
            font = self._get_best_font(32)
            text = artist_name if len(artist_name) <= 28 else artist_name[:25] + "..."
            tw = draw.textlength(text, font=font)
            
            draw.text(((w-tw)/2 + 2, (h-32)/2 + 2), text, fill=(20, 30, 50), font=font)
            draw.text(((w-tw)/2, (h-32)/2), text, fill=(235, 240, 255), font=font)
            
            out = Path(self.images_dir) / f"{track_id}_artist.png"
            img.save(out, "PNG")
            logger.info(f"🖼️ Создан placeholder: {out}")
            return str(out)
        except Exception as e:
            logger.error(f"❌ Ошибка placeholder: {e}")
            return str(Path(self.images_dir) / f"{track_id}_artist.png")

    def _get_best_font(self, size: int):
        import platform
        system = platform.system().lower()
        if system == "windows":
            paths = ["C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"]
        elif system == "darwin":
            paths = ["/System/Library/Fonts/SFNS.ttf", "/System/Library/Fonts/Helvetica.ttc", "/System/Library/Fonts/Arial.ttf"]
        else:
            paths = ["/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
        for font_path in paths:
            try:
                if font_path.endswith('.ttc'):
                    return ImageFont.truetype(font_path, size, index=0)
                else:
                    return ImageFont.truetype(font_path, size)
            except:
                continue
        return ImageFont.load_default()

    def _cache_push(self, artist_key: str, url: str):
        # Используем нижний регистр для ключей кэша
        artist_key_lower = artist_key.lower()
        arr = self.photo_cache.get(artist_key_lower, [])
        if url not in arr:
            arr.insert(0, url)
            self.photo_cache[artist_key_lower] = arr[:20]
            self._save_photo_cache()

# Глобальный экземпляр
image_searcher = SimpleArtistImageSearch()