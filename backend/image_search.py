# -*- coding: utf-8 -*-
import os, io, re, json, logging, requests
from pathlib import Path
from typing import List, Optional
from PIL import Image, ImageOps, ImageFile, ImageDraw, ImageFont
from difflib import SequenceMatcher
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
        
        # Проверяем что результат адекватный
        img = Image.open(io.BytesIO(output_bytes))
        if img.mode == 'RGBA':
            # Проверяем что не вырезано пол-изображения
            alpha = img.getchannel('A')
            alpha_data = list(alpha.getdata())
            transparent_pixels = sum(1 for a in alpha_data if a < 10)
            total_pixels = len(alpha_data)
            
            if transparent_pixels > total_pixels * 0.8:  # Слишком много прозрачного
                logger.warning("⚠️ Rembg вырезал слишком много, используем оригинал")
                # Возвращаем оригинал с белым фоном
                original_img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
                bg = Image.new("RGB", original_img.size, (255, 255, 255))
                bg.paste(original_img, (0, 0))
                buf = io.BytesIO()
                bg.save(buf, format="PNG")
                return buf.getvalue()
        
        return output_bytes
    except Exception as e:
        raise RuntimeError(f"Rembg error: {e}")

# ----------------- Ультра-умный парсер имен -----------------
def similarity(a: str, b: str) -> float:
    """Вычисляет схожесть двух строк"""
    a = a.lower().strip()
    b = b.lower().strip()
    return SequenceMatcher(None, a, b).ratio()

def normalize_artist_name(name: str) -> str:
    """Нормализует имя артиста для поиска"""
    name = name.lower().strip()
    
    # Убираем восклицательные знаки, пунктуацию
    name = re.sub(r'[!?.,;:"]', '', name)
    
    # Замены символов и слов
    replacements = {
        'ё': 'е', 'ъ': '', 'ь': '',
        '$': 's', '&': 'and', '+': 'and',
        ' group': '', ' band': '', ' группа': '', ' банд': '',
        '!': '', '?': '', '.': '', ',': ''
    }
    
    for old, new in replacements.items():
        name = name.replace(old, new)
    
    # Убираем лишние пробелы
    name = re.sub(r'\s+', ' ', name).strip()
    
    return name

def generate_smart_variants(artist_name: str) -> List[str]:
    """Генерирует умные варианты для поиска"""
    variants = set()
    
    # Основные варианты
    variants.add(artist_name)
    variants.add(artist_name.lower())
    variants.add(artist_name.upper())
    variants.add(artist_name.title())
    
    # Без пунктуации
    clean_name = re.sub(r'[!?.,;:"()]', '', artist_name)
    variants.add(clean_name)
    variants.add(clean_name.lower())
    
    # Нормализованные версии
    normalized = normalize_artist_name(artist_name)
    variants.add(normalized)
    variants.add(normalized.replace(' ', '_'))
    variants.add(normalized.replace(' ', ''))
    
    # Популярные замены
    common_replacements = [
        ('ё', 'е'), ('Ё', 'Е'),
        ('$', 's'), ('&', 'and'), 
        ('+', 'and'), ('!', ''),
        (' group', ''), (' band', ''),
        (' группа', ''), (' банд', ''),
        ('brothers', 'brother'), ('sisters', 'sister'),
        ('crew', ''), ('family', ''),
        ('max', 'макс'), ('макс', 'max'),
        ('anna', 'анна'), ('анна', 'anna'),
        ('alex', 'алекс'), ('алекс', 'alex'),
    ]
    
    current_name = artist_name
    for old, new in common_replacements:
        if old in current_name.lower():
            replaced = current_name.replace(old, new).replace(old.title(), new)
            variants.add(replaced)
            variants.add(replaced.lower())
            current_name = replaced
    
    # Для конкретных артистов
    specific_mappings = {
        'руки вверх!': 'руки вверх',
        'максим': 'макс',
        'макsим': 'максим', 
        'макс': 'максим',
        'гаяз': 'gayaz',
        'gayazov': 'gayaz',
        'анна асти': 'anna asti',
        'anna asti': 'анна асти',
    }
    
    for original, replacement in specific_mappings.items():
        if original in artist_name.lower():
            variants.add(replacement)
            variants.add(replacement.upper())
            variants.add(replacement.title())
    
    # Убираем дубликаты и пустые строки
    return sorted([v for v in variants if v and len(v) > 1], key=len, reverse=True)

# ----------------- Утилиты -----------------
def slugify(s: str) -> str:
    s = re.sub(r"[^\w\s.-]+", "", s, flags=re.U)
    s = re.sub(r"\s+", "_", s.strip(), flags=re.U)
    return s[:140].lower()

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

    def _find_local_artist_photo(self, artist_name: str) -> Optional[str]:
        if not os.path.exists(self.artists_dir):
            return None
        
        logger.info(f"🔍 Ультра-умный поиск локального фото для: '{artist_name}'")
        
        # Генерируем умные варианты
        search_names = generate_smart_variants(artist_name)
        logger.info(f"🔍 Варианты поиска ({len(search_names)}): {search_names[:8]}")
        
        supported_extensions = ['.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif']
        all_files = list(Path(self.artists_dir).glob("*"))
        
        # Сначала ищем точные совпадения
        for search_name in search_names:
            for ext in supported_extensions:
                # Прямое совпадение
                direct_path = os.path.join(self.artists_dir, f"{search_name}{ext}")
                if os.path.exists(direct_path):
                    logger.info(f"📁 Найдено точное совпадение: {direct_path}")
                    return direct_path
                
                # Совпадение без учета регистра
                for file_path in all_files:
                    if file_path.stem.lower() == search_name.lower() and file_path.suffix.lower() in supported_extensions:
                        logger.info(f"📁 Найдено совпадение (регистр): {file_path}")
                        return str(file_path)
        
        # Затем ищем по схожести
        best_match = None
        best_similarity = 0.7  # Минимальная схожесть
        
        for file_path in all_files:
            if file_path.suffix.lower() not in supported_extensions:
                continue
                
            filename = file_path.stem
            for search_name in search_names:
                sim = similarity(filename, search_name)
                if sim > best_similarity:
                    best_similarity = sim
                    best_match = str(file_path)
                    logger.info(f"📁 Найдено по схожести {sim:.2f}: {filename} ~ {search_name}")
        
        if best_match:
            logger.info(f"✅ Выбрано лучшее совпадение: {best_match} (схожесть: {best_similarity:.2f})")
            return best_match
        
        logger.info(f"🔍 Локальное фото для '{artist_name}' не найдено")
        return None

    def _search_yandex_music_smart(self, artist_name: str) -> Optional[str]:
        """Умный поиск в Яндекс.Музыке с выбором лучшего фото"""
        try:
            from yandex_music import Client as YandexClient
            
            YANDEX_MUSIC_TOKEN = "y0__xC-3q2iAxje-AYglImpghUw9pW0kAgCx0SZ5vnWcYWpiGpLqwVPsGWEfg"

                
            client = YandexClient(YANDEX_MUSIC_TOKEN).init()
            search_result = client.search(artist_name)
            
            if not search_result or not search_result.artists:
                logger.info(f"🔍 Яндекс.Музыка: артист '{artist_name}' не найден")
                return None
                
            # Берем самого релевантного артиста
            artist = search_result.artists.results[0]
            
            # Пробуем разные источники фото в порядке приоритета
            photo_sources = []
            
            # 1. Основное фото (cover)
            if hasattr(artist, 'cover') and artist.cover:
                cover_uri = getattr(artist.cover, 'uri', None)
                if cover_uri:
                    photo_url = f"https://{cover_uri.replace('%%', '1000x1000')}"
                    photo_sources.append(("cover", photo_url))
            
            # 2. OG image
            if hasattr(artist, 'og_image') and artist.og_image:
                og_image_url = artist.og_image.replace('%%', '1000x1000')
                photo_sources.append(("og_image", og_image_url))
            
            # 3. Composer cover (для композиторов)
            if hasattr(artist, 'composer') and artist.composer and hasattr(artist.composer, 'cover') and artist.composer.cover:
                composer_uri = getattr(artist.composer.cover, 'uri', None)
                if composer_uri:
                    photo_url = f"https://{composer_uri.replace('%%', '1000x1000')}"
                    photo_sources.append(("composer", photo_url))
            
            if not photo_sources:
                logger.info(f"🔍 Яндекс.Музыка: у артиста '{artist_name}' нет фото")
                return None
            
            # Возвращаем лучшее фото (cover имеет наивысший приоритет)
            best_photo = photo_sources[0][1]
            logger.info(f"✅ Яндекс.Музыка: найдено {len(photo_sources)} фото, выбрано: {best_photo}")
            return best_photo
            
        except Exception as e:
            logger.warning(f"⚠️ Ошибка поиска в Яндекс.Музыке: {e}")
            return None

    def _process_photo_smart(self, image_data: bytes, track_id: int, source: str = "internet") -> Optional[str]:
        """Умная обработка фото с улучшенным удалением фона"""
        try:
            img = Image.open(io.BytesIO(image_data))
            w, h = img.size
            
            # Проверяем размер и пропорции
            if w < MIN_W or h < MIN_H or not ok_aspect(w, h): 
                logger.warning(f"⚠️ Плохое изображение: {w}x{h}")
                return None
            
            # Нормализуем размер
            img = normalize_img(img, min_side=1024)
            out_path = Path(self.images_dir) / f"{track_id}_artist.png"

            # Для локальных PNG с прозрачностью - пропускаем удаление фона
            if source == "local" and img.mode == 'RGBA':
                alpha = img.getchannel('A')
                alpha_data = list(alpha.getdata())
                has_transparency = any(a < 255 for a in alpha_data)
                
                if has_transparency:
                    logger.info("🖼️ PNG с прозрачностью - фон не трогаем")
                    img.save(out_path, "PNG")
                    return str(out_path)

            # Умное удаление фона
            if self.use_rembg and _ensure_rembg():
                try:
                    png_bytes = smart_remove_background(image_data)
                    with open(out_path, "wb") as f:
                        f.write(png_bytes)
                    logger.info(f"✅ Фото обработано (умное удаление фона): {out_path}")
                    return str(out_path)
                except Exception as e:
                    logger.warning(f"⚠️ Умное удаление фона не удалось: {e}")

            # Fallback - просто сохраняем как есть
            img.save(out_path, "PNG", optimize=True)
            logger.info(f"✅ Фото сохранено (без удаления фона): {out_path}")
            return str(out_path)
                
        except Exception as e:
            logger.error(f"❌ Ошибка обработки фото: {e}")
            return None

    def fetch_artist_png(self, artist_name: str, track_id: int, use_rembg: bool = True):
        """Умный поиск фото с улучшенным парсингом и обработкой"""
        original_rembg_setting = self.use_rembg
        self.use_rembg = use_rembg
        
        try:
            cache_key = f"{artist_name}_{track_id}_{use_rembg}"
            if cache_key in self.artist_cache:
                return self.artist_cache[cache_key]
            
            logger.info(f"🎭 УМНЫЙ поиск фото для: '{artist_name}' (ID: {track_id})")
            
            # 1. Локальные фото (приоритет)
            local_photo = self._find_local_artist_photo(artist_name)
            if local_photo:
                try:
                    with open(local_photo, "rb") as f:
                        image_data = f.read()
                    processed_path = self._process_photo_smart(image_data, track_id, "local")
                    if processed_path:
                        self.artist_cache[cache_key] = processed_path
                        self._cache_push(artist_name.strip().lower(), f"local://{local_photo}")
                        logger.info(f"✅ Использовано локальное фото: {local_photo}")
                        return processed_path
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка обработки локального фото: {e}")

            # 2. Яндекс.Музыка (умный поиск)
            url = self._search_yandex_music_smart(artist_name)
            if url:
                image_data = download_bytes(url)
                if image_data:
                    processed_path = self._process_photo_smart(image_data, track_id, "internet")
                    if processed_path:
                        self._cache_push(artist_name.strip().lower(), url)
                        self.artist_cache[cache_key] = processed_path
                        logger.info(f"✅ Найдено в Яндекс.Музыке: {url}")
                        return processed_path

            # 3. Placeholder
            p = self._create_placeholder_image(artist_name, track_id)
            self.artist_cache[cache_key] = p
            logger.info("🖼️ Создан placeholder")
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
            # Красивый градиентный фон
            img = Image.new("RGB", (w, h), (60, 75, 115))
            draw = ImageDraw.Draw(img)
            
            # Добавляем легкий градиент
            for i in range(h):
                r = max(40, min(60, 40 + i//20))
                g = max(55, min(75, 55 + i//25)) 
                b = max(95, min(115, 95 + i//15))
                draw.line([(0, i), (w, i)], fill=(r, g, b))
            
            font = self._get_best_font(32)
            text = artist_name if len(artist_name) <= 28 else artist_name[:25] + "..."
            tw = draw.textlength(text, font=font)
            
            # Красивая тень
            draw.text(((w-tw)/2 + 2, (h-32)/2 + 2), text, fill=(20, 30, 50), font=font)
            # Основной текст
            draw.text(((w-tw)/2, (h-32)/2), text, fill=(235, 240, 255), font=font)
            
            out = Path(self.images_dir) / f"{track_id}_artist.png"
            img.save(out, "PNG")
            logger.info(f"🖼️ Создан красивый placeholder: {out}")
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
        arr = self.photo_cache.get(artist_key, [])
        if url not in arr:
            arr.insert(0, url)
            self.photo_cache[artist_key] = arr[:20]
            self._save_photo_cache()

# Глобальный экземпляр
image_searcher = SimpleArtistImageSearch()