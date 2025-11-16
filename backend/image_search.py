# -*- coding: utf-8 -*-
import os, io, re, json, logging, requests
import numpy as np
from pathlib import Path
from typing import List, Optional
from PIL import Image, ImageOps, ImageFile, ImageDraw, ImageFont, ImageFilter
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)
ImageFile.LOAD_TRUNCATED_IMAGES = True

# ----------------- Константы/настройки -----------------
MIN_W, MIN_H = 512, 512
ASPECT_MIN, ASPECT_MAX = 0.75, 1.8
TIMEOUT = 15

# ----------------- Улучшенный Rembg с мягкой вырезкой -----------------
_REMBG_AVAILABLE = None
_REMBG_FUNCTION = None

def _ensure_rembg():
    global _REMBG_AVAILABLE, _REMBG_FUNCTION
    if _REMBG_AVAILABLE is None:
        try:
            from rembg import remove
            _REMBG_FUNCTION = remove
            _REMBG_AVAILABLE = True
            logger.info("✅ Rembg загружен")
        except ImportError:
            _REMBG_AVAILABLE = False
            logger.warning("❌ Rembg не установлен")
    return _REMBG_AVAILABLE

def soft_background_removal(image_bytes: bytes) -> bytes:
    """
    Мягкое удаление фона с rembg и улучшенной постобработкой
    """
    if not _ensure_rembg():
        return add_solid_background(image_bytes, (255, 255, 255))
    
    try:
        # Пробуем разные модели для лучшего результата
        models_to_try = ['u2net', 'u2netp', 'u2net_human_seg', 'isnet-general-use']
        
        best_result = None
        best_score = 0
        
        for model in models_to_try:
            try:
                logger.info(f"🔧 Пробуем модель: {model}")
                output_bytes = _REMBG_FUNCTION(image_bytes, model=model)
                
                # Оцениваем качество вырезки
                score = evaluate_removal_quality(output_bytes)
                logger.info(f"📊 Модель {model}: оценка {score:.2f}")
                
                if score > best_score:
                    best_score = score
                    best_result = output_bytes
                    
                # Если отличный результат, используем его
                if score > 0.8:
                    break
                    
            except Exception as e:
                logger.warning(f"⚠️ Модель {model} не сработала: {e}")
                continue
        
        if best_result and best_score > 0.3:  # Минимальный порог качества
            # Улучшаем результат
            improved_result = improve_removal_result(best_result)
            logger.info(f"✅ Успешная вырезка, оценка: {best_score:.2f}")
            return improved_result
        else:
            logger.warning("❌ Все модели дали плохой результат, используем fallback")
            return add_solid_background(image_bytes, (240, 240, 240))
            
    except Exception as e:
        logger.error(f"❌ Ошибка вырезки фона: {e}")
        return add_solid_background(image_bytes, (245, 245, 245))

def evaluate_removal_quality(image_bytes: bytes) -> float:
    """Оценивает качество вырезки фона"""
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
        img_array = np.array(img)
        
        # Анализируем альфа-канал
        alpha = img_array[:, :, 3]
        
        # Процент непрозрачных пикселей (должен быть разумным)
        opaque_pixels = np.sum(alpha > 0)
        total_pixels = alpha.size
        opaque_ratio = opaque_pixels / total_pixels
        
        # Баланс - не слишком много и не слишком мало непрозрачных пикселей
        if opaque_ratio < 0.1 or opaque_ratio > 0.9:
            return 0.1  # Слишком много или слишком мало объекта
        
        # Оцениваем равномерность краев
        edge_quality = evaluate_edge_quality(alpha)
        
        # Итоговая оценка
        score = min(opaque_ratio * 0.6 + edge_quality * 0.4, 1.0)
        return score
        
    except Exception:
        return 0.0

def evaluate_edge_quality(alpha: np.ndarray) -> float:
    """Оценивает качество краев вырезки"""
    try:
        from scipy import ndimage
        
        # Находим границы
        structure = np.ones((3, 3))
        eroded = ndimage.binary_erosion(alpha > 0, structure=structure)
        edges = (alpha > 0) & ~eroded
        
        # Анализируем гладкость границ
        edge_pixels = np.sum(edges)
        if edge_pixels == 0:
            return 0.0
            
        # Проверяем на резкие переходы (плохие края)
        edge_values = alpha[edges]
        smooth_edges = np.sum((edge_values > 50) & (edge_values < 200))
        smooth_ratio = smooth_edges / edge_pixels
        
        return smooth_ratio
        
    except Exception:
        return 0.5

def improve_removal_result(image_bytes: bytes) -> bytes:
    """Улучшает результат вырезки - сглаживает края и добавляет мягкий фон"""
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
        
        # Создаем мягкую тень/подложку
        result = add_soft_shadow(img)
        
        # Сохраняем
        buf = io.BytesIO()
        result.save(buf, format="PNG", optimize=True)
        return buf.getvalue()
        
    except Exception as e:
        logger.warning(f"⚠️ Улучшение не удалось: {e}")
        return image_bytes

def add_soft_shadow(img: Image.Image) -> Image.Image:
    """Добавляет мягкую тень для лучшего визуального восприятия"""
    # Создаем слегка размытую версию для мягких краев
    blurred = img.filter(ImageFilter.GaussianBlur(2))
    
    # Увеличиваем контраст альфа-канала для четкости
    alpha = blurred.getchannel('A')
    alpha = alpha.point(lambda x: 0 if x < 50 else 255)  # Бинаризуем альфа-канал
    
    # Применяем улучшенный альфа-канал
    result = img.copy()
    result.putalpha(alpha)
    
    return result

def add_solid_background(image_bytes: bytes, bg_color: tuple) -> bytes:
    """Добавляет однотонный фон к изображению"""
    try:
        img = Image.open(io.BytesIO(image_bytes))
        
        if img.mode == 'RGBA':
            # Создаем фон
            background = Image.new("RGB", img.size, bg_color)
            # Аккуратно накладываем изображение на фон
            background.paste(img, (0, 0), img)
            img = background
        
        # Немного улучшаем качество
        img = img.filter(ImageFilter.SMOOTH_MORE)
        
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        logger.info(f"🎨 Добавлен фон RGB{bg_color}")
        return buf.getvalue()
        
    except Exception as e:
        logger.error(f"❌ Ошибка добавления фона: {e}")
        return image_bytes

def smart_background_processing(image_bytes: bytes) -> bytes:
    """
    Умная обработка фона с перебором вариантов
    """
    # Сначала пробуем мягкую вырезку
    logger.info("🎯 Начинаем умную обработку фона...")
    
    # Вариант 1: Мягкая вырезка с rembg
    removed_bg = soft_background_removal(image_bytes)
    
    # Проверяем результат
    quality_score = evaluate_removal_quality(removed_bg)
    logger.info(f"📊 Оценка вырезки: {quality_score:.2f}")
    
    if quality_score > 0.5:
        logger.info("✅ Используем вырезку с rembg")
        return removed_bg
    else:
        # Пробуем разные фоны
        background_colors = [
            (255, 255, 255),    # Белый
            (240, 240, 240),    # Светло-серый
            (245, 245, 245),    # Очень светлый серый
            (250, 250, 250),    # Почти белый
            (255, 250, 240),    # Теплый белый
        ]
        
        best_result = None
        best_score = 0
        
        for color in background_colors:
            try:
                colored_bg = add_solid_background(image_bytes, color)
                score = evaluate_background_quality(colored_bg)
                
                if score > best_score:
                    best_score = score
                    best_result = colored_bg
                    
                logger.info(f"🎨 Фон {color}: оценка {score:.2f}")
                
            except Exception as e:
                logger.warning(f"⚠️ Ошибка с фоном {color}: {e}")
                continue
        
        if best_result and best_score > 0.3:
            logger.info(f"✅ Выбран фон с оценкой {best_score:.2f}")
            return best_result
        else:
            # Fallback - белый фон
            logger.info("🔄 Используем fallback (белый фон)")
            return add_solid_background(image_bytes, (255, 255, 255))

def evaluate_background_quality(image_bytes: bytes) -> float:
    """Оценивает качество изображения с фоном"""
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        img_array = np.array(img)
        
        # Анализируем контраст и детализацию
        gray = np.dot(img_array[...,:3], [0.2989, 0.5870, 0.1140])
        contrast = np.std(gray)  # Стандартное отклонение как мера контраста
        
        # Нормализуем оценку
        score = min(contrast / 50.0, 1.0)
        return score
        
    except Exception:
        return 0.5

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

# ----------------- Функции для работы с Яндекс токеном -----------------
def load_yandex_token():
    """Загружает Яндекс токен из файла"""
    try:
        BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        YANDEX_TOKEN_FILE = os.path.join(BASE_DIR, "config", "yandex_token.txt")
        
        if os.path.exists(YANDEX_TOKEN_FILE):
            with open(YANDEX_TOKEN_FILE, 'r', encoding='utf-8') as f:
                token = f.read().strip()
                if token:
                    logger.info("✅ Яндекс токен загружен из файла")
                    return token
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки Яндекс токена: {e}")
    
    return None

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
        
        self.use_background_removal = True

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
        bad_chars = '!\"№;%:?*()_-+=@#$%^&\\/'
        for ch in bad_chars:
            s = s.replace(ch, '')
        s = re.sub(r'\s+', ' ', s).strip()
        return s

    def _find_local_artist_photo(self, artist_name: str) -> Optional[str]:
        if not os.path.exists(self.artists_dir):
            return None

        logger.info(f"🔍 Поиск локального фото для: '{artist_name}'")
        supported_ext = {'.jpg', '.jpeg', '.png', '.webp'}
        
        query_clean = self._clean_name(artist_name).lower()

        for f in Path(self.artists_dir).iterdir():
            if f.suffix.lower() not in supported_ext:
                continue
            if self._clean_name(f.stem).lower() == query_clean:
                logger.info(f"✅ Найден локальный файл: {f}")
                return str(f)
        return None

    def _search_yandex_music_smart(self, artist_name: str) -> Optional[str]:
        """Улучшенный поиск фото артистов в Яндекс.Музыке"""
        try:
            from yandex_music import Client as YandexClient
            
            yandex_token = load_yandex_token()
            if not yandex_token:
                logger.warning("❌ Яндекс токен не найден")
                return None
                
            client = YandexClient(yandex_token).init()
            search_result = client.search(artist_name)
            
            if not search_result or not search_result.artists:
                logger.info(f"🔍 Яндекс.Музыка: артист '{artist_name}' не найден")
                return None
                
            artist = search_result.artists.results[0]
            
            # ПРИОРИТЕТ 1: Основное фото артиста (cover)
            if hasattr(artist, 'cover') and artist.cover:
                cover_uri = getattr(artist.cover, 'uri', None)
                if cover_uri:
                    photo_url = f"https://{cover_uri.replace('%%', '1000x1000')}"
                    logger.info(f"✅ Найдено основное фото артиста: {photo_url}")
                    return photo_url
            
            # ПРИОРИТЕТ 2: OG изображение
            if hasattr(artist, 'og_image') and artist.og_image:
                og_image_url = artist.og_image.replace('%%', '1000x1000')
                logger.info(f"✅ Найдено OG изображение: {og_image_url}")
                return og_image_url
            
            # ПРИОРИТЕТ 3: Фото из последних альбомов
            if hasattr(artist, 'albums') and artist.albums:
                # Берем последние альбомы (более актуальные фото)
                recent_albums = sorted(artist.albums, 
                                     key=lambda x: getattr(x, 'year', 0), 
                                     reverse=True)[:5]
                
                for album in recent_albums:
                    if hasattr(album, 'cover_uri') and album.cover_uri:
                        album_photo_url = f"https://{album.cover_uri.replace('%%', '1000x1000')}"
                        logger.info(f"✅ Найдено фото из альбома ({getattr(album, 'year', 'N/A')}): {album_photo_url}")
                        return album_photo_url
            
            logger.info(f"🔍 Для артиста '{artist_name}' не найдено подходящих фото")
            return None
            
        except Exception as e:
            logger.warning(f"⚠️ Ошибка поиска в Яндекс.Музыке: {e}")
            return None

    def _process_internet_photo(self, image_data: bytes, track_id: int) -> Optional[str]:
        try:
            img = Image.open(io.BytesIO(image_data))
            w, h = img.size
            
            if w < MIN_W or h < MIN_H or not ok_aspect(w, h): 
                logger.warning(f"⚠️ Плохое интернет-изображение: {w}x{h}")
                return None
            
            img = normalize_img(img, min_side=1024)
            out_path = Path(self.images_dir) / f"{track_id}_artist.png"

            if self.use_background_removal:
                try:
                    # Используем умную обработку фона
                    processed_bytes = smart_background_processing(image_data)
                    with open(out_path, "wb") as f:
                        f.write(processed_bytes)
                    
                    logger.info(f"✅ Фото обработано с умным фоном: {out_path}")
                    return str(out_path)
                    
                except Exception as e:
                    logger.warning(f"⚠️ Обработка фона не удалась: {e}")
                    # Fallback: сохраняем оригинал
                    img.save(out_path, "PNG", optimize=True)
                    return str(out_path)

            # Если обработка отключена
            img.save(out_path, "PNG", optimize=True)
            logger.info(f"✅ Фото сохранено без обработки: {out_path}")
            return str(out_path)
                
        except Exception as e:
            logger.error(f"❌ Ошибка обработки интернет-фото: {e}")
            return None

    def _use_local_photo_as_is(self, local_path: str, track_id: int) -> str:
        try:
            out_path = Path(self.images_dir) / f"{track_id}_artist.png"
            
            img = Image.open(local_path)
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

    def fetch_artist_png(self, artist_name: str, track_id: int, use_background_removal: bool = True):
        original_setting = self.use_background_removal
        self.use_background_removal = use_background_removal
        
        try:
            cache_key = f"{artist_name.lower()}_{track_id}_{use_background_removal}"
            if cache_key in self.artist_cache:
                return self.artist_cache[cache_key]
            
            logger.info(f"🎭 Поиск фото для: '{artist_name}' (ID: {track_id})")
            
            # Приоритет локальных файлов
            local_photo = self._find_local_artist_photo(artist_name)
            if local_photo:
                logger.info(f"📁 ЛОКАЛЬНЫЙ ФАЙЛ НАЙДЕН!")
                processed_path = self._use_local_photo_as_is(local_photo, track_id)
                self.artist_cache[cache_key] = processed_path
                self._cache_push(artist_name.strip().lower(), f"local://{local_photo}")
                return processed_path

            # Поиск в Яндекс.Музыке
            logger.info(f"🔍 Ищем в Яндекс.Музыке...")
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
            self.use_background_removal = original_setting

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
        artist_key_lower = artist_key.lower()
        arr = self.photo_cache.get(artist_key_lower, [])
        if url not in arr:
            arr.insert(0, url)
            self.photo_cache[artist_key_lower] = arr[:20]
            self._save_photo_cache()

# Глобальный экземпляр
image_searcher = SimpleArtistImageSearch()