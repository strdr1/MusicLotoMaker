# -*- coding: utf-8 -*-
import os, io, re, json, hashlib, logging, requests
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import quote
from PIL import Image, ImageOps, ImageFile, ImageDraw, ImageFont
from rembg import remove
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)
ImageFile.LOAD_TRUNCATED_IMAGES = True

# ----------------- Константы/настройки -----------------
MIN_W, MIN_H = 512, 512
ASPECT_MIN, ASPECT_MAX = 0.75, 1.8  # портреты чаще 3:4..16:9
TIMEOUT = 15
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")
HDRS = {"User-Agent": UA, "Accept-Language": "ru,en;q=0.9"}

# Источники, с которых портреты приходят чаще корректные
TRUSTED = (
    "wikipedia.org", "wikimedia.org", "commons.wikimedia.org",
    "ru.wikipedia.org", "en.wikipedia.org", "discogs.com", "last.fm",
    "imdb.com", "kinoteatr.ru", "kino-teatr.ru"
)

# Явные индикаторы «обложек/артов», которых избегаем
COVER_HINTS = ("album", "cover", "single", "artwork", "vinyl", "discography")

# ----------------- Утилиты -----------------
def slugify(s: str) -> str:
    s = re.sub(r"[^\w\s.-]+", "", s, flags=re.U)
    s = re.sub(r"\s+", "_", s.strip(), flags=re.U)
    return s[:140].lower()

def ok_aspect(w: int, h: int) -> bool:
    if w <= 0 or h <= 0: return False
    r = h / float(w)
    return ASPECT_MIN <= r <= ASPECT_MAX

def is_coverish_url(u: str) -> bool:
    u = u.lower()
    return any(tok in u for tok in COVER_HINTS)

def is_trusted(u: str) -> bool:
    u = u.lower()
    return any(dom in u for dom in TRUSTED)

def normalize_img(img: Image.Image, min_side: int = 900) -> Image.Image:
    img = ImageOps.exif_transpose(img.convert("RGBA"))
    w, h = img.size
    scale = max(1.0, min_side / float(min(w, h)))
    if scale > 1.01:
        img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
    return img

def save_png_or_jpg(img: Image.Image, path: Path, use_rembg: bool = False) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    ext = path.suffix.lower()
    
    if use_rembg:
        try:
            # Сохраняем как PNG с удалением фона
            png_bytes = remove(img.tobytes())
            with open(path.with_suffix(".png"), "wb") as f:
                f.write(png_bytes)
            return path.with_suffix(".png")
        except Exception as e:
            logger.warning(f"⚠️ rembg error, fallback без вырезания: {e}")
    
    if ext == ".png":
        img.save(path, "PNG", optimize=True)
    else:
        img.save(path.with_suffix(".jpg"), "JPEG", quality=88, optimize=True, progressive=True)
        path = path.with_suffix(".jpg")
    return path

def download_bytes(url: str) -> Optional[bytes]:
    try:
        r = requests.get(url, headers=HDRS, timeout=TIMEOUT, stream=True)
        r.raise_for_status()
        return r.content
    except Exception as e:
        logger.debug(f"download fail: {e}")
        return None

# ----------------- Основной класс -----------------
class SimpleArtistImageSearch:
    def __init__(self):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.images_dir = os.path.join(self.base_dir, "images")
        self.artists_dir = os.path.join(self.base_dir, "artists")  # Новая папка с фото артистов
        os.makedirs(self.images_dir, exist_ok=True)
        os.makedirs(self.artists_dir, exist_ok=True)  # Создаем папку если её нет

        self.artist_cache = {}
        self.photo_cache_file = os.path.join(self.base_dir, "artist_photo_cache.json")
        self._load_photo_cache()

    # ---------- кэш ----------
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

    # ---------- поиск в локальной папке artists ----------
    def _find_local_artist_photo(self, artist_name: str) -> Optional[str]:
        """
        Ищет фото артиста в папке artists по имени.
        Поддерживает разные форматы и варианты имен.
        """
        if not os.path.exists(self.artists_dir):
            return None

        # Используем metadata_processor для получения канонического имени артиста
        try:
            from processors.metadata_processor import create_metadata_processor
            metadata_processor = create_metadata_processor()
            
            # Создаем тестовый filename для парсера
            test_filename = f"{artist_name} - test.mp3"
            parsed = metadata_processor.process(test_filename)
            canonical_artist = parsed.get("artist", artist_name)
            
            logger.info(f"🔍 Поиск локального фото для: '{artist_name}' -> '{canonical_artist}'")
            
        except Exception as e:
            logger.warning(f"⚠️ Не удалось использовать metadata_processor: {e}")
            canonical_artist = artist_name

        # Варианты имен для поиска
        search_names = [
            canonical_artist,
            artist_name,
            canonical_artist.lower(),
            artist_name.lower(),
            canonical_artist.upper(),
            slugify(canonical_artist),
            slugify(artist_name),
        ]
        
        # Убираем дубликаты
        search_names = list(set([name for name in search_names if name.strip()]))

        supported_extensions = ['.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif']
        
        for search_name in search_names:
            for ext in supported_extensions:
                # Прямое совпадение
                direct_path = os.path.join(self.artists_dir, f"{search_name}{ext}")
                if os.path.exists(direct_path):
                    logger.info(f"📁 Найдено локальное фото: {direct_path}")
                    return direct_path
                
                # Поиск файлов, начинающихся с имени артиста
                pattern = f"{search_name}*{ext}"
                for file_path in Path(self.artists_dir).glob(pattern):
                    if file_path.is_file():
                        logger.info(f"📁 Найдено локальное фото по паттерну: {file_path}")
                        return str(file_path)

        logger.info(f"🔍 Локальное фото для '{artist_name}' не найдено")
        return None

    def _process_local_photo(self, local_path: str, track_id: int) -> Optional[str]:
        """Обрабатывает локальное фото из папки artists БЕЗ удаления фона"""
        try:
            with Image.open(local_path) as img:
                w, h = img.size

                # Базовые валидации
                if w < MIN_W or h < MIN_H:
                    logger.warning(f"⚠️ Локальное фото слишком маленькое: {w}x{h}")
                    return None
                if not ok_aspect(w, h):
                    logger.warning(f"⚠️ Локальное фото неподходящего соотношения: {w}x{h}")
                    return None

                img = normalize_img(img, min_side=1024)
                
                # Сохраняем в images директорию БЕЗ удаления фона
                ext = Path(local_path).suffix.lower()
                output_path = Path(self.images_dir) / f"{track_id}_artist{ext}"
                
                if ext == '.png':
                    img.save(output_path, "PNG", optimize=True)
                else:
                    img.save(output_path, "JPEG", quality=88, optimize=True, progressive=True)
                
                logger.info(f"✅ Локальное фото сохранено (фон не удален): {output_path}")
                return str(output_path)

        except Exception as e:
            logger.error(f"❌ Ошибка обработки локального фото: {e}")
            return None

    def _process_internet_photo(self, image_data: bytes, track_id: int, use_rembg: bool = True) -> Optional[str]:
        """Обрабатывает фото из интернета С удалением фона"""
        try:
            img = Image.open(io.BytesIO(image_data))
            w, h = img.size

            # Базовые валидации
            if w < MIN_W or h < MIN_H: 
                return None
            if not ok_aspect(w, h): 
                return None

            img = normalize_img(img, min_side=1024)

            # Для интернет-фото используем удаление фона
            out_path = Path(self.images_dir) / f"{track_id}_artist.png"
            if use_rembg:
                try:
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    png_bytes = remove(image_data)
                    with open(out_path, "wb") as f:
                        f.write(png_bytes)
                    logger.info(f"✅ Интернет-фото сохранено (фон удален): {out_path}")
                    return str(out_path)
                except Exception as e:
                    logger.warning(f"⚠️ rembg error, fallback без вырезания: {e}")

            # fallback без удаления фона
            img.save(out_path, "PNG", optimize=True)
            logger.info(f"✅ Интернет-фото сохранено (без удаления фона): {out_path}")
            return str(out_path)

        except Exception as e:
            logger.debug(f"_process_internet_photo fail: {e}")
            return None

    # ---------- публичные методы ----------
    def fetch_artist_png(self, artist_name: str, track_id: int, use_rembg: bool = True):
        """
        Возвращает путь к PNG/JPG с портретом артиста для конкретного трека.
        Приоритет: локальная папка artists -> cache -> Wikimedia/Wikipedia -> Google CSE -> Яндекс -> placeholder.
        """
        cache_key = f"{artist_name}_{track_id}"
        if cache_key in self.artist_cache:
            return self.artist_cache[cache_key]

        try:
            logger.info(f"🎭 Поиск фото для: {artist_name}")

            # 0) Локальная папка artists (ВЫСШИЙ ПРИОРИТЕТ) - БЕЗ удаления фона
            local_photo = self._find_local_artist_photo(artist_name)
            if local_photo:
                try:
                    processed_path = self._process_local_photo(local_photo, track_id)
                    if processed_path:
                        self.artist_cache[cache_key] = processed_path
                        
                        # Сохраняем в кэш для будущего использования
                        artist_key = artist_name.strip().lower()
                        self._cache_push(artist_key, f"local://{local_photo}")
                        
                        return processed_path
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка обработки локального фото: {e}")

            # 1) cache по артисту (только интернет-ссылки)
            artist_key = artist_name.strip().lower()
            if artist_key in self.photo_cache and self.photo_cache[artist_key]:
                for url in self.photo_cache[artist_key]:
                    # Пропускаем локальные ссылки, если они уже не сработали
                    if url.startswith("local://"):
                        continue
                    p = self._download_process_and_store(url, track_id, use_rembg)
                    if p: 
                        self.artist_cache[cache_key] = p
                        return p

            # 2) Wikimedia/Wikipedia — детерминированно (интернет - с удалением фона)
            url = self._wikimedia_best(artist_name)
            if url:
                p = self._download_process_and_store(url, track_id, use_rembg)
                if p:
                    self._cache_push(artist_key, url)
                    self.artist_cache[cache_key] = p
                    return p

            # 3) Google CSE (интернет - с удалением фона)
            urls = self._search_google_faces(artist_name, count=8)
            for u in urls:
                p = self._download_process_and_store(u, track_id, use_rembg)
                if p:
                    self._cache_push(artist_key, u)
                    self.artist_cache[cache_key] = p
                    return p

            # 4) Яндекс (интернет - с удалением фона)
            urls = self._search_yandex_simple(artist_name)
            for u in urls:
                p = self._download_process_and_store(u, track_id, use_rembg)
                if p:
                    self._cache_push(artist_key, u)
                    self.artist_cache[cache_key] = p
                    return p

            # 5) fallback
            p = self._create_placeholder_image(artist_name, track_id)
            self.artist_cache[cache_key] = p
            return p

        except Exception as e:
            logger.error(f"💥 Критическая ошибка: {e}")
            p = self._create_placeholder_image(artist_name, track_id)
            self.artist_cache[cache_key] = p
            return p

    def fetch_multiple_artist_photos(self, artist_name: str, count: int = 10) -> List[str]:
        """Возвращает список URL кандидатов (портретов), приоритет — локальные -> Wikimedia -> Google CSE."""
        out: List[str] = []
        artist_key = artist_name.strip().lower()

        # 0) локальные фото
        local_photo = self._find_local_artist_photo(artist_name)
        if local_photo:
            out.append(f"local://{local_photo}")

        # cache
        cached = self.photo_cache.get(artist_key, [])
        # Фильтруем локальные ссылки из кэша
        cached = [url for url in cached if not url.startswith("local://")]
        if cached: 
            out += cached

        # wikimedia
        w = self._wikimedia_best(artist_name)
        if w: 
            out.append(w)

        # google faces
        out += self._search_google_faces(artist_name, count=count)

        # yandex (в конце)
        out += self._search_yandex_simple(artist_name)

        # нормализация/дедуп
        seen, uniq = set(), []
        for u in out:
            if u.startswith("local://"):
                base = u
            else:
                base = u.split("?")[0]
            if base in seen: 
                continue
            seen.add(base)
            uniq.append(u)

        # фильтр «анти-обложка» (только для интернет-ссылок)
        uniq = [u for u in uniq if u.startswith("local://") or not is_coverish_url(u)]
        uniq = uniq[:max(1, count)]

        # кэшируем
        if uniq:
            self.photo_cache[artist_key] = uniq
            self._save_photo_cache()

        logger.info(f"✅ Всего найдено уникальных фото: {len(uniq)}")
        return uniq

    # ---------- приватные: загрузка/обработка ----------
    def _download_process_and_store(self, url: str, track_id: int, use_rembg: bool = True) -> Optional[str]:
        """Скачивает и обрабатывает фото из интернета С удалением фона"""
        try:
            # Для локальных ссылок используем отдельный метод (без удаления фона)
            if url.startswith("local://"):
                local_path = url.replace("local://", "")
                return self._process_local_photo(local_path, track_id)
            
            # Для интернет-ссылок - скачиваем и обрабатываем с удалением фона
            raw = download_bytes(url)
            if not raw: 
                return None
                
            return self._process_internet_photo(raw, track_id, use_rembg)

        except Exception as e:
            logger.debug(f"_download_process_and_store fail: {e}")
            return None

    def _cache_push(self, artist_key: str, url: str):
        arr = self.photo_cache.get(artist_key, [])
        if url not in arr:
            arr.insert(0, url)
            self.photo_cache[artist_key] = arr[:20]
            self._save_photo_cache()

    # ---------- Wikimedia / Wikipedia ----------
    def _wikimedia_best(self, artist_name: str) -> Optional[str]:
        """
        1) Пытаемся найти Wikidata Q-id по имени артиста.
        2) Если найден P18 (основное изображение) — строим прямой URL в Commons (thumb 1200px).
        3) Иначе берём pageimage из Wikipedia (ru→en).
        """
        try:
            qid = self._wikidata_qid(artist_name)
            if qid:
                img_name = self._wikidata_p18(qid)
                if img_name:
                    # Commons file -> URL
                    safe = quote(img_name.replace(" ", "_"))
                    return f"https://commons.wikimedia.org/wiki/Special:FilePath/{safe}?width=1200"
        except Exception:
            pass

        # pageimage ru-wiki
        u = self._wikipedia_pageimage(artist_name, lang="ru")
        if u: return u
        # fallback en-wiki
        return self._wikipedia_pageimage(artist_name, lang="en")

    def _wikidata_qid(self, name: str) -> Optional[str]:
        # wbsearchentities по human name
        try:
            params = {
                "action": "wbsearchentities", "format": "json",
                "language": "ru", "limit": 5, "type": "item", "search": name
            }
            r = requests.get("https://www.wikidata.org/w/api.php", params=params, headers=HDRS, timeout=TIMEOUT)
            r.raise_for_status()
            hits = r.json().get("search", [])
            # выбираем человека/исполнителя
            for h in hits:
                desc = (h.get("description") or "").lower()
                if any(tok in desc for tok in ("пев", "музыкан", "исполн", "singer", "musician", "artist")):
                    return h.get("id")
            return hits[0]["id"] if hits else None
        except Exception:
            return None

    def _wikidata_p18(self, qid: str) -> Optional[str]:
        try:
            params = {"action": "wbgetclaims", "format": "json", "entity": qid, "property": "P18"}
            r = requests.get("https://www.wikidata.org/w/api.php", params=params, headers=HDRS, timeout=TIMEOUT)
            r.raise_for_status()
            claims = r.json().get("claims", {}).get("P18", [])
            if not claims: return None
            val = claims[0]["mainsnak"]["datavalue"]["value"]
            return val  # file name on Commons
        except Exception:
            return None

    def _wikipedia_pageimage(self, name: str, lang: str = "ru") -> Optional[str]:
        try:
            # Сначала ищем страницу
            sr = requests.get(
                f"https://{lang}.wikipedia.org/w/api.php",
                params={"action":"query","list":"search","srsearch":name,"format":"json","srlimit":5},
                headers=HDRS, timeout=TIMEOUT
            ).json()
            pages = sr.get("query", {}).get("search", [])
            if not pages: return None
            title = pages[0]["title"]

            # Получаем pageimage/thumbnail
            q = requests.get(
                f"https://{lang}.wikipedia.org/w/api.php",
                params={"action":"query","prop":"pageimages","format":"json","piprop":"thumbnail|name","pithumbsize":1200,"titles":title},
                headers=HDRS, timeout=TIMEOUT
            ).json()
            pages = q.get("query", {}).get("pages", {})
            for _, pdata in pages.items():
                thumb = pdata.get("thumbnail", {})
                src = thumb.get("source")
                if src: return src
            return None
        except Exception:
            return None

    # ---------- Google CSE (только портреты лиц) ----------
    def _search_google_faces(self, artist_name: str, count: int = 8) -> List[str]:
        api_key = os.getenv('GOOGLE_API_KEY')
        cx = os.getenv('GOOGLE_SEARCH_ENGINE_ID')
        if not api_key or not cx:
            logger.info("⚠️ Google CSE ключи не заданы — пропускаем")
            return []
        try:
            params = {
                "q": f'{artist_name} portrait photo -album -cover -single -artwork',
                "key": api_key,
                "cx": cx,
                "searchType": "image",
                "num": min(10, max(1, count)),
                "imgType": "face",         # <— ключевой параметр
                "safe": "active",
                "imgSize": "large"
            }
            r = requests.get("https://www.googleapis.com/customsearch/v1", params=params, timeout=TIMEOUT)
            if r.status_code != 200:
                logger.warning(f"Google CSE HTTP {r.status_code}")
                return []
            data = r.json()
            items = data.get("items", []) or []
            out = []
            for it in items:
                link = it.get("link") or ""
                if not link: continue
                if is_coverish_url(link) and not is_trusted(link): 
                    continue
                out.append(link)
            return out
        except Exception as e:
            logger.warning(f"Google CSE error: {e}")
            return []

    # ---------- Яндекс (низкий приоритет, без гарантий) ----------
    def _search_yandex_simple(self, artist_name: str) -> List[str]:
        try:
            q = f"{artist_name} фото портрет".replace(" ", "+")
            url = f"https://yandex.ru/images/search?text={q}"
            r = requests.get(url, headers=HDRS, timeout=TIMEOUT)
            if r.status_code != 200: return []
            # грубый HTML-парс: берём большие картинки и отбрасываем «обложки»
            urls = []
            for m in re.finditer(r'"url":"(https:[^"]+)"', r.text):
                u = m.group(1).encode().decode("unicode_escape")
                if any(u.lower().endswith(ext) for ext in (".jpg",".jpeg",".png",".webp")):
                    if not is_coverish_url(u):
                        urls.append(u)
                if len(urls) >= 8: break
            return urls
        except Exception:
            return []

    # ---------- placeholder ----------
    def _create_placeholder_image(self, artist_name: str, track_id: int) -> str:
        try:
            w, h = 600, 600
            img = Image.new("RGB", (w,h), (40,55,95))
            draw = ImageDraw.Draw(img)
            font = self._get_best_font(36)
            text = artist_name if len(artist_name)<=32 else artist_name[:29]+"..."
            tw, th = draw.textlength(text, font=font), 36
            draw.text(((w-tw)/2, (h-th)/2), text, fill=(235,240,255), font=font)
            out = Path(self.images_dir) / f"{track_id}_artist.png"
            img.save(out, "PNG")
            logger.info(f"🖼️ Placeholder: {out}")
            return str(out)
        except Exception as e:
            logger.error(f"❌ Ошибка placeholder: {e}")
            return str(Path(self.images_dir) / f"{track_id}_artist.png")

    def _get_best_font(self, size: int):
        paths = [
            "C:/Windows/Fonts/arial.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/System/Library/Fonts/Arial.ttf",
            "arial.ttf","Arial.ttf"
        ]
        for p in paths:
            try:
                return ImageFont.truetype(p, size)
            except: pass
        return ImageFont.load_default()


# Глобальный экземпляр
image_searcher = SimpleArtistImageSearch()