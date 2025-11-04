# -*- coding: utf-8 -*-
import os, io, re, json, hashlib, logging, requests, time
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import quote
from PIL import Image, ImageOps, ImageFile, ImageDraw, ImageFont
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)
ImageFile.LOAD_TRUNCATED_IMAGES = True

# ----------------- Константы/настройки -----------------
MIN_W, MIN_H = 512, 512
ASPECT_MIN, ASPECT_MAX = 0.75, 1.8
TIMEOUT = 15
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")
HDRS = {"User-Agent": UA, "Accept-Language": "ru,en;q=0.9"}

TRUSTED = (
    "wikipedia.org", "wikimedia.org", "commons.wikimedia.org",
    "ru.wikipedia.org", "en.wikipedia.org", "discogs.com", "last.fm",
    "imdb.com", "kinoteatr.ru", "kino-teatr.ru"
)

COVER_HINTS = ("album", "cover", "single", "artwork", "vinyl", "discography")

# ----------------- Hugging Face Background Removal -----------------
HF_TOKEN = os.getenv("HF_TOKEN")
HF_MODEL = "briaai/RMBG-1.4"
HF_API_URL = f"https://api-inference.huggingface.co/models/{HF_MODEL}"

def hf_remove_background(image_bytes: bytes) -> bytes:
    """
    Удаляет фон через Hugging Face Inference API.
    Возвращает PNG-байты с альфа-каналом.
    """
    if not HF_TOKEN:
        raise ValueError("HF_TOKEN не задан в .env")

    headers = {"Authorization": f"Bearer {HF_TOKEN}"}
    response = requests.post(HF_API_URL, headers=headers, data=image_bytes, timeout=30)

    if response.status_code == 200:
        return response.content
    else:
        error_msg = response.json().get("error", response.text) if response.content else "No response"
        raise RuntimeError(f"HF API error ({response.status_code}): {error_msg}")

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
            buf = io.BytesIO()
            img_format = "PNG" if img.mode == "RGBA" else "JPEG"
            img.save(buf, format=img_format, quality=90 if img_format == "JPEG" else None)
            raw_bytes = buf.getvalue()
            png_bytes = hf_remove_background(raw_bytes)
            out_path = path.with_suffix(".png")
            with open(out_path, "wb") as f:
                f.write(png_bytes)
            return out_path
        except Exception as e:
            logger.warning(f"⚠️ HF background removal error, fallback без вырезания: {e}")
    
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
        self.artists_dir = os.path.join(self.base_dir, "artists")
        os.makedirs(self.images_dir, exist_ok=True)
        os.makedirs(self.artists_dir, exist_ok=True)

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
        if not os.path.exists(self.artists_dir):
            return None
        try:
            from processors.metadata_processor import create_metadata_processor
            metadata_processor = create_metadata_processor()
            test_filename = f"{artist_name} - test.mp3"
            parsed = metadata_processor.process(test_filename)
            canonical_artist = parsed.get("artist", artist_name)
            logger.info(f"🔍 Поиск локального фото для: '{artist_name}' -> '{canonical_artist}'")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось использовать metadata_processor: {e}")
            canonical_artist = artist_name

        search_names = list(set(filter(None, [
            canonical_artist, artist_name,
            canonical_artist.lower(), artist_name.lower(),
            canonical_artist.upper(), slugify(canonical_artist),
            slugify(artist_name)
        ])))

        supported_extensions = ['.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif']
        for search_name in search_names:
            for ext in supported_extensions:
                direct_path = os.path.join(self.artists_dir, f"{search_name}{ext}")
                if os.path.exists(direct_path):
                    logger.info(f"📁 Найдено локальное фото: {direct_path}")
                    return direct_path
                pattern = f"{search_name}*{ext}"
                for file_path in Path(self.artists_dir).glob(pattern):
                    if file_path.is_file():
                        logger.info(f"📁 Найдено локальное фото по паттерну: {file_path}")
                        return str(file_path)
        logger.info(f"🔍 Локальное фото для '{artist_name}' не найдено")
        return None

    def _process_local_photo(self, local_path: str, track_id: int) -> Optional[str]:
        try:
            with open(local_path, "rb") as f:
                raw = f.read()
            img_original = Image.open(io.BytesIO(raw))

            has_alpha = img_original.mode == "RGBA" and "A" in img_original.getbands()
            if local_path.lower().endswith(".png") and has_alpha:
                logger.info(f"🖼️ PNG с прозрачностью — фон не обрабатываем: {local_path}")
                img = img_original.convert("RGBA")
            else:
                logger.info(f"✂️ Удаляем фон через HF для: {local_path}")
                try:
                    png_bytes = hf_remove_background(raw)
                    img = Image.open(io.BytesIO(png_bytes))
                    if img.mode != "RGBA":
                        img = img.convert("RGBA")
                except Exception as e:
                    logger.warning(f"⚠️ HF fallback на оригинал: {e}")
                    img = img_original.convert("RGBA")

            out_path = Path(self.images_dir) / f"{track_id}_artist.png"
            img.save(out_path, "PNG")
            logger.info(f"✅ Фото артиста сохранено: {out_path}")
            return str(out_path)
        except Exception as e:
            logger.error(f"❌ Ошибка _process_local_photo: {e}")
            return None

    def _process_internet_photo(self, image_data: bytes, track_id: int, use_rembg: bool = True) -> Optional[str]:
        try:
            img = Image.open(io.BytesIO(image_data))
            w, h = img.size
            if w < MIN_W or h < MIN_H or not ok_aspect(w, h): 
                return None
            img = normalize_img(img, min_side=1024)
            out_path = Path(self.images_dir) / f"{track_id}_artist.png"

            if use_rembg:
                try:
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    png_bytes = hf_remove_background(image_data)
                    with open(out_path, "wb") as f:
                        f.write(png_bytes)
                    logger.info(f"✅ Интернет-фото сохранено (фон удалён через HF): {out_path}")
                    return str(out_path)
                except Exception as e:
                    logger.warning(f"⚠️ HF background removal failed, fallback: {e}")

            img.save(out_path, "PNG", optimize=True)
            logger.info(f"✅ Интернет-фото сохранено (без удаления фона): {out_path}")
            return str(out_path)
        except Exception as e:
            logger.debug(f"_process_internet_photo fail: {e}")
            return None

    # ---------- улучшенный поиск в Wikipedia ----------
    def _wikipedia_enhanced_search(self, artist_name: str) -> Optional[str]:
        try:
            search_variants = [
                artist_name,
                f"{artist_name} musician",
                f"{artist_name} singer", 
                f"{artist_name} band",
                f"{artist_name} artist"
            ]
            languages = ['ru', 'en', 'de', 'fr']
            for lang in languages:
                for search_query in search_variants:
                    url = self._wikipedia_pageimage(search_query, lang)
                    if url:
                        logger.info(f"✅ Wikipedia ({lang}): найдено фото для {artist_name}")
                        return url
            return None
        except Exception as e:
            logger.debug(f"Enhanced Wikipedia search failed: {e}")
            return None

    # ---------- поиск через MusicBrainz ----------
    def _search_musicbrainz(self, artist_name: str) -> Optional[str]:
        try:
            search_url = "https://musicbrainz.org/ws/2/artist"
            params = {
                "query": f'artist:"{artist_name}"',
                "fmt": "json",
                "limit": 1
            }
            response = requests.get(search_url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                artists = data.get('artists', [])
                if artists:
                    artist_id = artists[0]['id']
                    cover_art_url = f"https://coverartarchive.org/artist/{artist_id}"
                    response = requests.get(cover_art_url, timeout=10)
                    if response.status_code == 200:
                        cover_data = response.json()
                        images = cover_data.get('images', [])
                        for image in images:
                            if image.get('front', True):
                                image_url = image['image']
                                logger.info(f"✅ MusicBrainz: найдено фото для {artist_name}")
                                return image_url
            return None
        except Exception as e:
            logger.debug(f"MusicBrainz search failed: {e}")
            return None

    # ---------- поиск через Discogs ----------
    def _search_discogs(self, artist_name: str) -> Optional[str]:
        try:
            api_key = os.getenv('DISCOGS_API_KEY')
            if not api_key:
                return None
            headers = {
                'User-Agent': 'MusicApp/1.0',
                'Authorization': f'Discogs token={api_key}'
            }
            search_url = "https://api.discogs.com/database/search"
            params = {
                "q": artist_name,
                "type": "artist",
                "per_page": 1
            }
            response = requests.get(search_url, params=params, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                results = data.get('results', [])
                if results:
                    artist_data = results[0]
                    image_url = artist_data.get('cover_image')
                    if image_url and not is_coverish_url(image_url):
                        logger.info(f"✅ Discogs: найдено фото для {artist_name}")
                        return image_url
            return None
        except Exception as e:
            logger.debug(f"Discogs search failed: {e}")
            return None

    # ---------- умный поиск в Google Images ----------
    def _search_google_smart(self, artist_name: str, count: int = 8) -> List[str]:
        try:
            api_key = os.getenv('GOOGLE_API_KEY')
            cx = os.getenv('GOOGLE_SEARCH_ENGINE_ID')
            if not api_key or not cx:
                return []
            search_queries = [
                f'{artist_name} portrait -album -cover -single',
                f'{artist_name} photo -album -cover',
                f'{artist_name} musician portrait',
                f'{artist_name} singer photo',
                f'{artist_name} official photo',
                f'{artist_name} press photo'
            ]
            all_urls = []
            for query in search_queries:
                if len(all_urls) >= count:
                    break
                params = {
                    "q": query,
                    "key": api_key, 
                    "cx": cx,
                    "searchType": "image", 
                    "num": min(5, count - len(all_urls)),
                    "imgType": "face", 
                    "safe": "active", 
                    "imgSize": "large",
                    "rights": "cc_publicdomain"
                }
                r = requests.get("https://www.googleapis.com/customsearch/v1", params=params, timeout=TIMEOUT)
                if r.status_code == 200:
                    items = r.json().get("items", []) or []
                    for item in items:
                        url = item.get("link")
                        if (url and 
                            not is_coverish_url(url) and 
                            url not in all_urls and
                            self._is_good_image_url(url)):
                            all_urls.append(url)
            return all_urls[:count]
        except Exception as e:
            logger.warning(f"Google smart search error: {e}")
            return []

    def _is_good_image_url(self, url: str) -> bool:
        try:
            bad_domains = ['wiki', 'wikipedia', 'last.fm', 'discogs']
            if any(domain in url.lower() for domain in bad_domains):
                return False
            good_extensions = ['.jpg', '.jpeg', '.png', '.webp']
            if not any(url.lower().endswith(ext) for ext in good_extensions):
                return False
            return True
        except:
            return False

    # ---------- улучшенный Яндекс поиск ----------
    def _search_yandex_enhanced(self, artist_name: str) -> List[str]:
        try:
            queries = [
                f"{artist_name} фото портрет",
                f"{artist_name} музыкант фото",
                f"{artist_name} певец фото",
                f"{artist_name} официальное фото"
            ]
            all_urls = []
            for query in queries:
                if len(all_urls) >= 8:
                    break
                q_encoded = query.replace(" ", "+")
                url = f"https://yandex.ru/images/search?text={q_encoded}&itype=jpg"
                r = requests.get(url, headers=HDRS, timeout=TIMEOUT)
                if r.status_code == 200:
                    import re
                    pattern = r'"url":"(https:[^"]+\.(?:jpg|jpeg|png|webp))"'
                    matches = re.findall(pattern, r.text)
                    for match in matches:
                        url = match.encode().decode("unicode_escape")
                        if (not is_coverish_url(url) and 
                            url not in all_urls and
                            self._is_good_image_url(url)):
                            all_urls.append(url)
                            if len(all_urls) >= 8:
                                break
            return all_urls[:8]
        except Exception:
            return []

    # ---------- поиск через социальные сети ----------
    def _search_social_media(self, artist_name: str) -> Optional[str]:
        try:
            instagram_urls = [
                f"https://www.instagram.com/{slugify(artist_name)}/",
                f"https://www.instagram.com/{slugify(artist_name.replace(' ', ''))}/"
            ]
            for url in instagram_urls:
                try:
                    response = requests.head(url, timeout=5, allow_redirects=True)
                    if response.status_code == 200:
                        logger.info(f"🔍 Найден Instagram для {artist_name}")
                except:
                    continue
            return None
        except Exception as e:
            logger.debug(f"Social media search failed: {e}")
            return None

    # ---------- Wikimedia / Wikipedia ----------
    def _wikimedia_best(self, artist_name: str) -> Optional[str]:
        try:
            qid = self._wikidata_qid(artist_name)
            if qid:
                img_name = self._wikidata_p18(qid)
                if img_name:
                    safe = quote(img_name.replace(" ", "_"))
                    return f"https://commons.wikimedia.org/wiki/Special:FilePath/{safe}?width=1200"
        except Exception:
            pass
        u = self._wikipedia_pageimage(artist_name, lang="ru")
        if u: return u
        return self._wikipedia_pageimage(artist_name, lang="en")

    def _wikidata_qid(self, name: str) -> Optional[str]:
        try:
            params = {"action": "wbsearchentities", "format": "json", "language": "ru", "limit": 5, "type": "item", "search": name}
            r = requests.get("https://www.wikidata.org/w/api.php", params=params, headers=HDRS, timeout=TIMEOUT)
            r.raise_for_status()
            hits = r.json().get("search", [])
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
            return claims[0]["mainsnak"]["datavalue"]["value"]
        except Exception:
            return None

    def _wikipedia_pageimage(self, name: str, lang: str = "ru") -> Optional[str]:
        try:
            sr = requests.get(f"https://{lang}.wikipedia.org/w/api.php",
                              params={"action":"query","list":"search","srsearch":name,"format":"json","srlimit":5},
                              headers=HDRS, timeout=TIMEOUT).json()
            pages = sr.get("query", {}).get("search", [])
            if not pages: return None
            title = pages[0]["title"]
            q = requests.get(f"https://{lang}.wikipedia.org/w/api.php",
                             params={"action":"query","prop":"pageimages","format":"json","piprop":"thumbnail|name","pithumbsize":1200,"titles":title},
                             headers=HDRS, timeout=TIMEOUT).json()
            pages = q.get("query", {}).get("pages", {})
            for _, pdata in pages.items():
                thumb = pdata.get("thumbnail", {})
                src = thumb.get("source")
                if src: return src
            return None
        except Exception:
            return None

    # ---------- Google CSE ----------
    def _search_google_faces(self, artist_name: str, count: int = 8) -> List[str]:
        api_key = os.getenv('GOOGLE_API_KEY')
        cx = os.getenv('GOOGLE_SEARCH_ENGINE_ID')
        if not api_key or not cx:
            logger.info("⚠️ Google CSE ключи не заданы — пропускаем")
            return []
        try:
            params = {
                "q": f'{artist_name} portrait photo -album -cover -single -artwork',
                "key": api_key, "cx": cx,
                "searchType": "image", "num": min(10, max(1, count)),
                "imgType": "face", "safe": "active", "imgSize": "large"
            }
            r = requests.get("https://www.googleapis.com/customsearch/v1", params=params, timeout=TIMEOUT)
            if r.status_code != 200:
                logger.warning(f"Google CSE HTTP {r.status_code}")
                return []
            items = r.json().get("items", []) or []
            out = [it.get("link") for it in items if it.get("link") and (is_trusted(it.get("link")) or not is_coverish_url(it.get("link")))]
            return out
        except Exception as e:
            logger.warning(f"Google CSE error: {e}")
            return []

    # ---------- Яндекс ----------
    def _search_yandex_simple(self, artist_name: str) -> List[str]:
        try:
            q = f"{artist_name} фото портрет".replace(" ", "+")
            url = f"https://yandex.ru/images/search?text={q}"
            r = requests.get(url, headers=HDRS, timeout=TIMEOUT)
            if r.status_code != 200: return []
            urls = []
            for m in re.finditer(r'"url":"(https:[^"]+)"', r.text):
                u = m.group(1).encode().decode("unicode_escape")
                if any(u.lower().endswith(ext) for ext in (".jpg",".jpeg",".png",".webp")) and not is_coverish_url(u):
                    urls.append(u)
                if len(urls) >= 8: break
            return urls
        except Exception:
            return []

    # ---------- улучшенный публичный метод ----------
    def fetch_artist_png(self, artist_name: str, track_id: int, use_rembg: bool = True):
        cache_key = f"{artist_name}_{track_id}"
        if cache_key in self.artist_cache:
            return self.artist_cache[cache_key]
        
        try:
            logger.info(f"🎭 Улучшенный поиск фото для: {artist_name}")
            
            # 1. Локальные фото
            local_photo = self._find_local_artist_photo(artist_name)
            if local_photo:
                try:
                    processed_path = self._process_local_photo(local_photo, track_id)
                    if processed_path:
                        self.artist_cache[cache_key] = processed_path
                        self._cache_push(artist_name.strip().lower(), f"local://{local_photo}")
                        logger.info(f"✅ Найдено локальное фото: {local_photo}")
                        return processed_path
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка обработки локального фото: {e}")

            # 2. Кэш ранее найденных URL
            artist_key = artist_name.strip().lower()
            if artist_key in self.photo_cache:
                for url in self.photo_cache[artist_key]:
                    if url.startswith("local://"):
                        continue
                    p = self._download_process_and_store(url, track_id, use_rembg)
                    if p: 
                        self.artist_cache[cache_key] = p
                        logger.info(f"✅ Найдено в кэше: {url}")
                        return p

            # 3. Улучшенный Wikipedia поиск
            url = self._wikipedia_enhanced_search(artist_name)
            if url:
                p = self._download_process_and_store(url, track_id, use_rembg)
                if p:
                    self._cache_push(artist_key, url)
                    self.artist_cache[cache_key] = p
                    logger.info(f"✅ Найдено в Wikipedia: {url}")
                    return p

            # 4. MusicBrainz
            url = self._search_musicbrainz(artist_name)
            if url:
                p = self._download_process_and_store(url, track_id, use_rembg)
                if p:
                    self._cache_push(artist_key, url)
                    self.artist_cache[cache_key] = p
                    logger.info(f"✅ Найдено в MusicBrainz: {url}")
                    return p

            # 5. Discogs
            url = self._search_discogs(artist_name)
            if url:
                p = self._download_process_and_store(url, track_id, use_rembg)
                if p:
                    self._cache_push(artist_key, url)
                    self.artist_cache[cache_key] = p
                    logger.info(f"✅ Найдено в Discogs: {url}")
                    return p

            # 6. Умный Google поиск
            urls = self._search_google_smart(artist_name, count=10)
            for u in urls:
                p = self._download_process_and_store(u, track_id, use_rembg)
                if p:
                    self._cache_push(artist_key, u)
                    self.artist_cache[cache_key] = p
                    logger.info(f"✅ Найдено в Google: {u}")
                    return p

            # 7. Улучшенный Яндекс поиск
            urls = self._search_yandex_enhanced(artist_name)
            for u in urls:
                p = self._download_process_and_store(u, track_id, use_rembg)
                if p:
                    self._cache_push(artist_key, u)
                    self.artist_cache[cache_key] = p
                    logger.info(f"✅ Найдено в Яндекс: {u}")
                    return p

            # 8. Оригинальный Google (резерв)
            urls = self._search_google_faces(artist_name, count=8)
            for u in urls:
                p = self._download_process_and_store(u, track_id, use_rembg)
                if p:
                    self._cache_push(artist_key, u)
                    self.artist_cache[cache_key] = p
                    logger.info(f"✅ Найдено в Google (резерв): {u}")
                    return p

            # 9. Оригинальный Яндекс (резерв)
            urls = self._search_yandex_simple(artist_name)
            for u in urls:
                p = self._download_process_and_store(u, track_id, use_rembg)
                if p:
                    self._cache_push(artist_key, u)
                    self.artist_cache[cache_key] = p
                    logger.info(f"✅ Найдено в Яндекс (резерв): {u}")
                    return p

            # 10. Социальные сети
            url = self._search_social_media(artist_name)
            if url:
                p = self._download_process_and_store(url, track_id, use_rembg)
                if p:
                    self._cache_push(artist_key, url)
                    self.artist_cache[cache_key] = p
                    logger.info(f"✅ Найдено в соцсетях: {url}")
                    return p

            # 11. Placeholder
            p = self._create_placeholder_image(artist_name, track_id)
            self.artist_cache[cache_key] = p
            logger.info("🖼️ Создан placeholder")
            return p
            
        except Exception as e:
            logger.error(f"💥 Критическая ошибка: {e}")
            p = self._create_placeholder_image(artist_name, track_id)
            self.artist_cache[cache_key] = p
            return p

    def fetch_multiple_artist_photos(self, artist_name: str, count: int = 10) -> List[str]:
        out: List[str] = []
        artist_key = artist_name.strip().lower()
        local_photo = self._find_local_artist_photo(artist_name)
        if local_photo:
            out.append(f"local://{local_photo}")
        cached = [url for url in self.photo_cache.get(artist_key, []) if not url.startswith("local://")]
        out += cached
        
        sources = [
            lambda: [self._wikipedia_enhanced_search(artist_name)] if self._wikipedia_enhanced_search(artist_name) else [],
            lambda: [self._search_musicbrainz(artist_name)] if self._search_musicbrainz(artist_name) else [],
            lambda: [self._search_discogs(artist_name)] if self._search_discogs(artist_name) else [],
            lambda: self._search_google_smart(artist_name, count=5),
            lambda: self._search_yandex_enhanced(artist_name),
            lambda: self._search_google_faces(artist_name, count=5),
            lambda: self._search_yandex_simple(artist_name),
        ]
        
        for source in sources:
            try:
                urls = source()
                out.extend(urls)
                if len(out) >= count * 2:
                    break
            except Exception as e:
                logger.debug(f"Source failed: {e}")
                continue
        
        seen, uniq = set(), []
        for u in out:
            if not u:
                continue
            base = u if u.startswith("local://") else u.split("?")[0]
            if base not in seen:
                seen.add(base)
                uniq.append(u)
        
        uniq = [u for u in uniq if u.startswith("local://") or not is_coverish_url(u)]
        uniq = uniq[:max(1, count)]
        
        if uniq:
            self.photo_cache[artist_key] = uniq
            self._save_photo_cache()
        
        logger.info(f"✅ Всего найдено уникальных фото: {len(uniq)}")
        return uniq

    # ---------- приватные: загрузка/обработка ----------
    def _download_process_and_store(self, url: str, track_id: int, use_rembg: bool = True) -> Optional[str]:
        try:
            if url.startswith("local://"):
                return self._process_local_photo(url.replace("local://", ""), track_id)
            raw = download_bytes(url)
            if not raw: return None
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

    # ---------- placeholder ----------
    def _create_placeholder_image(self, artist_name: str, track_id: int) -> str:
        try:
            w, h = 600, 600
            img = Image.new("RGB", (w,h), (40,55,95))
            draw = ImageDraw.Draw(img)
            font = self._get_best_font(36)
            text = artist_name if len(artist_name)<=32 else artist_name[:29]+"..."
            tw = draw.textlength(text, font=font)
            th = 36
            draw.text(((w-tw)/2, (h-th)/2), text, fill=(235,240,255), font=font)
            out = Path(self.images_dir) / f"{track_id}_artist.png"
            img.save(out, "PNG")
            logger.info(f"🖼️ Placeholder: {out}")
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

# Глобальный экземпляр
image_searcher = SimpleArtistImageSearch()