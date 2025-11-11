# === CORE FASTAPI ===
from fastapi import FastAPI, UploadFile, File, HTTPException, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

# === SYSTEM & PATHS ===
import os
import sys
from pathlib import Path
from datetime import datetime
import tempfile

# === LOGGING ===
import logging
from logging.handlers import TimedRotatingFileHandler

# === UTILS & LIBS ===
import json
import requests
from PIL import Image
import io
import asyncio
import aiohttp
from urllib.parse import quote
import re
from typing import List

# === INTERNAL MODULES ===
from backend.dropbox_storage import DropboxStorage
dropbox_storage = DropboxStorage()
PORT = int(os.environ.get("PORT", 8000))
from pydantic import BaseModel

class IDChangeRequest(BaseModel):
    new_id: int

class IDSwapRequest(BaseModel):
    track1_id: int
    track2_id: int
# === LOGGING CONFIGURATION ===
LOG_DIR = r"E:\1\MusicLotoMaker\MusicLotoMaker\logs"
os.makedirs(LOG_DIR, exist_ok=True)
log_filename = os.path.join(LOG_DIR, f"server_{datetime.now().strftime('%Y-%m-%d')}.log")

formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s", "%Y-%m-%d %H:%M:%S")

file_handler = TimedRotatingFileHandler(log_filename, when="midnight", backupCount=7, encoding="utf-8")
file_handler.setFormatter(formatter)
file_handler.setLevel(logging.INFO)

console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
console_handler.setLevel(logging.INFO)

root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.addHandler(file_handler)
root_logger.addHandler(console_handler)

logger = logging.getLogger(__name__)

# === FASTAPI APP INITIALIZATION ===
app = FastAPI(title="Music Loto Maker", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === frontend logging endpoint ===
@app.post("/api/log/frontend")
async def frontend_log(request: Request):
    try:
        data = await request.json()
        msg = data.get("msg") if isinstance(data, dict) else str(data)
        level = (data.get("level") if isinstance(data, dict) else "info") or "info"
        level = level.lower()
        if level == "error":
            logger.error(f"[FRONTEND] {msg}")
        elif level == "warn" or level == "warning":
            logger.warning(f"[FRONTEND] {msg}")
        else:
            logger.info(f"[FRONTEND] {msg}")
        return JSONResponse({"logged": True})
    except Exception as e:
        logger.error(f"Ошибка при логировании с фронта: {e}")
        return JSONResponse({"logged": False, "error": str(e)})

# Добавляем путь к процессорам
current_dir = os.path.dirname(__file__)
processors_path = os.path.join(current_dir, 'processors')
if processors_path not in sys.path:
    sys.path.append(processors_path)

logger.info(f"🔍 Поиск metadata_processor в: {processors_path}")

try:
    from metadata_processor import create_metadata_processor
    metadata_processor = create_metadata_processor()
    logger.info("✅ Metadata processor initialized successfully")
except ImportError as e:
    logger.warning(f"❌ Metadata processor import error: {e}. Using fallback processor.")
    # Fallback процессор
    class SimpleMetadataProcessor:
        def process(self, filename):
            name = os.path.splitext(filename)[0]
            if ' - ' in name:
                parts = name.split(' - ', 1)
                return {"artist": parts[0].strip(), "title": parts[1].strip()}
            elif '_' in name:
                parts = name.split('_', 1)
                return {"artist": parts[0].strip(), "title": parts[1].strip()}
            return {"artist": name, "title": ""}

    metadata_processor = SimpleMetadataProcessor()

# Добавляем текущую директорию в путь для импортов
if current_dir not in sys.path:
    sys.path.append(current_dir)

try:
    from media_library import MediaLibrary, normalize_track_string
    logger.info("✅ MediaLibrary imported successfully")
except ImportError as e:
    logger.error(f"❌ Ошибка импорта MediaLibrary: {e}")
    # Простая заглушка
    class MediaLibrary:
        def __init__(self):
            self.tracks = []
            self.next_id = 1

        def get_tracks(self):
            return self.tracks

        def add_track(self, file_path, original_filename):
            try:
                track_id = self.next_id
                self.next_id += 1
                track = {
                    'id': track_id,
                    'file_path': file_path,
                    'original_filename': original_filename,
                    'artist': 'Неизвестный исполнитель',
                    'title': 'Без названия',
                    'metadata': {},
                    'segment_start': 0,
                    'segment_duration': 30,
                    'image_path': None,
                    'created_at': datetime.now().isoformat()
                }
                self.tracks.append(track)
                logger.info(f"✅ Трек добавлен: {track['id']}")
                return track
            except Exception as e:
                logger.error(f"❌ Ошибка добавления трека: {e}")
                return None

        def update_track(self, track_id, track_data):
            for track in self.tracks:
                if track['id'] == track_id:
                    track.update(track_data)
                    return True
            return False

        def delete_track(self, track_id):
            self.tracks = [t for t in self.tracks if t['id'] != track_id]
            return True

        def clear(self):
            self.tracks.clear()
            return True

        def get_track(self, track_id):
            for track in self.tracks:
                if track['id'] == track_id:
                    return track
            return None

        def get_tracks_count(self):
            return len(self.tracks)

        def update_track_segment(self, track_id, start_time, duration):
            track = self.get_track(track_id)
            if track:
                track['segment_start'] = start_time
                track['segment_duration'] = duration
                return True
            return False

        def track_exists(self, artist, title):
            return False

        def find_duplicate_tracks(self, artist, title):
            return []

        def get_track_by_artist_title(self, artist, title):
            return None

    logger.info("✅ Используется заглушка MediaLibrary")

# Импорт современных генераторов
try:
    from presentation import ModernPresentationGenerator
    logger.info("✅ ModernPresentationGenerator imported successfully")
except ImportError as e:
    logger.warning(f"⚠️ ModernPresentationGenerator import error: {e}")
    class ModernPresentationGenerator:
        def generate_presentation_by_template(self, tracks, output_path, **kwargs):
            logger.info(f"🎲 Генерация презентации по шаблону для {len(tracks)} треков (fallback).")
            try:
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write("Presentation by PDF Template - Placeholder")
                return output_path, []
            except Exception as e:
                logger.error(f"❌ Ошибка генерации: {e}")
                return None, []

        def generate_presentation_from_template(self, template_id, tracks, output_path, **kwargs):
            try:
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(f"Template {template_id} - Placeholder")
                return output_path, []
            except Exception as e:
                logger.error(f"❌ Ошибка генерации по шаблону {template_id}: {e}")
                return None, []

        def generate_modern_pptx(self, tracks, output_path):
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write("Modern Presentation Placeholder")
            return output_path

        def generate_modern_pdf(self, tracks, output_path):
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write("Modern PDF Placeholder")
            return output_path

# ОТДЕЛЬНЫЙ ИМПОРТ TicketGenerator
try:
    from tickets import TicketGenerator
    logger.info("✅ TicketGenerator imported successfully")
except ImportError as e:
    logger.warning(f"⚠️ TicketGenerator import error: {e}")
    class TicketGenerator:
        def generate_modern_tickets(self, tracks, count=24, design=None):
            logger.info(f"🎫 Генерация современных билетов: {count} шт.")
            import os
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            tickets_folder = os.path.join("output", f"tickets_{timestamp}")
            os.makedirs(tickets_folder, exist_ok=True)
            
            for i in range(count):
                ticket_path = os.path.join(tickets_folder, f"ticket_{i+1:03d}.pdf")
                with open(ticket_path, 'w', encoding='utf-8') as f:
                    f.write(f"Ticket {i+1}")
            
            archive_path = os.path.join(tickets_folder, "all_tickets.pdf")
            with open(archive_path, 'w', encoding='utf-8') as f:
                f.write("All Tickets Archive")
                
            return tickets_folder

try:
    from audio_editor import audio_editor
    logger.info("✅ Audio editor imported successfully")
except ImportError as e:
    logger.warning(f"⚠️ Audio editor import error: {e}")
    class AudioEditor:
        def generate_waveform(self, file_path): return []
        def play_segment(self, file_path, start_time, duration): return True
        def stop_playback(self): return True
        def suggest_best_segment(self, file_path): return 30
        def extract_segment(self, file_path, start_time, duration, output_path): return output_path
        def process_track_complete(self, track_data, clip_path): return track_data
        def get_all_tracks_data(self): return []
    audio_editor = AudioEditor()

# Импорт image_searcher для поиска фото
try:
    from image_search import image_searcher
    logger.info("✅ Image searcher imported successfully")
except ImportError as e:
    logger.warning(f"⚠️ Image searcher import error: {e}")
    class SimpleImageSearcher:
        def fetch_artist_png(self, artist_name, track_id):
            logger.info(f"🎭 Поиск фото для: {artist_name}")
            return None
        def fetch_multiple_artist_photos(self, artist_name, count=10):
            logger.info(f"🎭 Поиск {count} фото для: {artist_name}")
            return [
                "https://via.placeholder.com/400x400/667eea/white?text=Artist+1",
                "https://via.placeholder.com/400x400/764ba2/white?text=Artist+2",
                "https://via.placeholder.com/400x400/f093fb/white?text=Artist+3"
            ][:count]
    image_searcher = SimpleImageSearcher()

# Директории
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

for folder in ["temp", "output", "uploads", "config", "images", "templates", "assets", "downloads", "assets/custom_buttons", "assets/backgrounds"]:
    folder_path = os.path.join(BASE_DIR, folder)
    os.makedirs(folder_path, exist_ok=True)
    logger.info(f"📁 Создана папка: {folder_path}")

# Статика фронтенда
if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
else:
    logger.warning(f"⚠️ Папка фронтенда не найдена: {FRONTEND_DIR}")

# =========================
# INITIALIZATION
# =========================

# Инициализация модулей
media_library = MediaLibrary()

# ЯВНАЯ ПРОВЕРКА И ЗАГРУЗКА КРИТИЧЕСКИХ ФАЙЛОВ ПРИ СТАРТЕ
logger.info("🔍 Проверка критических файлов...")

# Проверка base.pptx
base_path = os.path.join(BASE_DIR, "base.pptx")
if not os.path.exists(base_path):
    logger.info("📦 base.pptx не найден, скачиваем из Dropbox...")
    if dropbox_storage.download_base_pptx(base_path):
        file_size = os.path.getsize(base_path)
        logger.info(f"✅ base.pptx успешно скачан ({file_size / 1024 / 1024:.2f} MB)")
    else:
        logger.warning("⚠️ Не удалось скачать base.pptx, генерация презентаций будет недоступна")
else:
    file_size = os.path.getsize(base_path)
    logger.info(f"✅ base.pptx найден ({file_size / 1024 / 1024:.2f} MB)")

# Проверка и создание папки artists
artists_dir = os.path.join(BASE_DIR, "artists")
if not os.path.exists(artists_dir):
    logger.info(f"📁 Папка {artists_dir} не найдена. Создание папки...")
    os.makedirs(artists_dir, exist_ok=True)
    logger.info(f"✅ Папка создана: {artists_dir}")

# Проверка и загрузка фото артистов
local_files = os.listdir(artists_dir)
if len(local_files) == 0:
    logger.info(f"📂 Папка {artists_dir} пуста. Попытка загрузки фото из Dropbox...")
    try:
        photos_info = dropbox_storage.list_artist_photos()
        if photos_info:
            downloaded_count = 0
            for photo_info in photos_info:
                filename = photo_info['filename']
                dropbox_path = photo_info['dropbox_path']
                local_path = os.path.join(artists_dir, filename)

                if os.path.exists(local_path):
                    logger.debug(f"🖼️ Файл {filename} уже существует, пропуск")
                    continue

                try:
                    metadata, response = dropbox_storage.dbx.files_download(dropbox_path)
                    with open(local_path, 'wb') as f:
                        f.write(response.content)
                    downloaded_count += 1
                    logger.info(f"✅ Загружено фото: {filename}")
                except Exception as e:
                    logger.error(f"❌ Ошибка при скачивании фото {filename}: {e}")
            
            logger.info(f"📸 Загрузка завершена. Скачано {downloaded_count} фото")
        else:
            logger.info("🔍 В Dropbox в папке /artists не найдено фото.")
    except Exception as e:
        logger.error(f"❌ Ошибка при загрузке фото артистов из Dropbox: {e}")
else:
    # Подсчитываем только изображения
    image_files = [f for f in local_files if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))]
    logger.info(f"✅ Папка {artists_dir} содержит {len(image_files)} изображений из {len(local_files)} файлов")

# Проверка других необходимых папок
required_dirs = [
    "downloads", "uploads", "output", "temp", 
    "images", "templates", "assets", "config",
    "assets/custom_buttons", "assets/backgrounds"
]

for folder in required_dirs:
    folder_path = os.path.join(BASE_DIR, folder)
    if not os.path.exists(folder_path):
        os.makedirs(folder_path, exist_ok=True)
        logger.info(f"📁 Создана папка: {folder_path}")

# Инициализация генераторов
try:
    modern_presentation_gen = ModernPresentationGenerator("base.pptx")
    logger.info("✅ ModernPresentationGenerator инициализирован")
except Exception as e:
    logger.error(f"❌ Ошибка инициализации ModernPresentationGenerator: {e}")
    modern_presentation_gen = None

try:
    ticket_gen = TicketGenerator()
    logger.info("✅ TicketGenerator инициализирован")
except Exception as e:
    logger.error(f"❌ Ошибка инициализации TicketGenerator: {e}")
    ticket_gen = None

# Проверка доступности медиатеки
try:
    tracks_count = media_library.get_tracks_count()
    logger.info(f"🎵 Медиатека инициализирована, треков: {tracks_count}")
except Exception as e:
    logger.error(f"❌ Ошибка инициализации медиатеки: {e}")

# Подключение tickets router
try:
    from backend.server_tickets_router import router as tickets_router, set_dependencies
    logger.info("✅ server_tickets_router импортирован успешно!")
    
    # Передаем зависимости
    set_dependencies(media_library, ticket_gen)
    app.include_router(tickets_router)
    logger.info("✅ Tickets router подключен!")
except ImportError as e:
    logger.error(f"❌ Ошибка импорта tickets router: {e}")
except Exception as e:
    logger.error(f"❌ Другая ошибка при подключении tickets router: {e}")

# =========================
# YANDEX MUSIC DOWNLOAD WITH IMPROVED PROGRESS REPORTING
# =========================

# Глобальная переменная для отслеживания прогресса скачивания
download_status = {
    "is_running": False,
    "total": 0,
    "current": 0,
    "current_track": "",
    "results": [],
    "failed_tracks": [],
    "duplicate_tracks": [],
    "successful_tracks": []
}

@app.get("/api/download/status")
async def get_download_status():
    """Получить текущий статус скачивания"""
    return download_status

def update_download_status(current: int, current_track: str, results: list = None):
    """Обновить статус скачивания"""
    download_status["current"] = current
    download_status["current_track"] = current_track
    if results is not None:
        download_status["results"] = results
        # Автоматически классифицируем результаты для фронтенда
        download_status["successful_tracks"] = [r for r in results if r.get('success')]
        download_status["duplicate_tracks"] = [r for r in results if r.get('duplicate')]
        download_status["failed_tracks"] = [r for r in results if not r.get('success') and not r.get('duplicate')]

def parse_track_list(track_list_text: str) -> list:
    """Парсит текст со списком треков в структурированный формат"""
    tracks = []
    lines = track_list_text.strip().split('\n')
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        artist, title = parse_track_line(line)
        if artist or title:
            tracks.append({
                'original_line': line,
                'artist': artist,
                'title': title,
                'search_query': f"{artist} {title}" if artist and title else line
            })
    
    return tracks

def parse_track_line(line: str) -> tuple:
    """Парсит строку с информацией о треке"""
    # УДАЛЯЕМ НУМЕРАЦИЮ в начале строки
    line = re.sub(r'^\d+\.\s*', '', line)  # "1. ", "2. ", "123. "
    line = re.sub(r'^\d+\)\s*', '', line)  # "1) ", "2) "
    line = re.sub(r'^-\s*', '', line)      # "- "
    
    line = re.sub(r'[\(\)\[\]\{\}]', '', line).strip()
    
    separators = [' - ', ' – ', ' — ', ' | ']
    
    for sep in separators:
        if sep in line:
            parts = line.split(sep, 1)
            if len(parts) == 2:
                artist = parts[0].strip()
                title = parts[1].strip()
                return artist, title
    
    match = re.match(r'(.+?)\s+\((.+?)\)$', line)
    if match:
        title = match.group(1).strip()
        artist = match.group(2).strip()
        return artist, title
    
    return "", line

async def download_single_track(track_info: dict):
    """Скачивание одного трека с проверкой дубликатов и улучшенной обработкой ошибок"""
    artist = track_info.get("artist", "")
    title = track_info.get("title", "")
    
    logger.info(f"🔍 Обработка: {artist} - {title}")
    
    # ПРОВЕРКА ДУБЛИКАТА ПЕРЕД СКАЧИВАНИЕМ
    if media_library.track_exists(artist, title):
        existing_track = media_library.get_track_by_artist_title(artist, title)
        logger.warning(f"🚫 Дубликат, пропускаем: {artist} - {title} (ID: {existing_track['id']})")
        return {
            "success": False, 
            "error": f"Трек уже существует в медиатеке (ID: {existing_track['id']})",
            "artist": artist,
            "title": title,
            "duplicate": True,
            "existing_track_id": existing_track['id']
        }
    
    try:
        # Ищем трек в Яндекс.Музыке
        from yandex_music import Client as YandexClient
        
        def _sync_search():
            try:
                YANDEX_MUSIC_TOKEN = "y0__xC-3q2iAxje-AYglImpghUw9pW0kAgCx0SZ5vnWcYWpiGpLqwVPsGWEfg"
                client = YandexClient(YANDEX_MUSIC_TOKEN).init()
                search_result = client.search(f"{artist} {title}")
                
                if not search_result or not search_result.best:
                    return None, "Трек не найден в Яндекс.Музыке"
                
                best = search_result.best
                
                # ПРОВЕРЯЕМ ТИП РЕЗУЛЬТАТА
                if not hasattr(best, 'type') or not hasattr(best, 'result'):
                    return None, "Некорректный результат поиска"
                
                result_type = best.type
                result_obj = best.result
                
                logger.info(f"🔍 Тип результата для '{artist} - {title}': {result_type}")
                
                # Если это не трек, а артист, альбом и т.д. - это ошибка для нас
                if result_type != 'track':
                    if result_type == 'artist':
                        artist_name = getattr(result_obj, 'name', 'Неизвестный артист')
                        return None, f"Найден артист '{artist_name}', но не трек '{title}'"
                    elif result_type == 'album':
                        album_title = getattr(result_obj, 'title', 'Неизвестный альбом')
                        return None, f"Найден альбом '{album_title}', но не трек '{title}'"
                    elif result_type == 'playlist':
                        return None, f"Найден плейлист, но не трек '{artist} - {title}'"
                    elif result_type == 'podcast':
                        return None, f"Найден подкаст, но не трек '{artist} - {title}'"
                    elif result_type == 'podcast_episode':
                        return None, f"Найден эпизод подкаста, но не трек '{artist} - {title}'"
                    else:
                        return None, f"Найден объект типа '{result_type}', но не трек '{artist} - {title}'"
                
                # Теперь точно работаем с треком
                track = result_obj
                
                if not track:
                    return None, "Трек не найден в Яндекс.Музыке"
                
                # Получаем информацию для скачивания
                download_info_list = track.get_download_info()
                if not download_info_list:
                    return None, "Нет доступных ссылок для скачивания"
                
                # Ищем подходящий формат для скачивания (предпочтительно MP3)
                best_download_info = None
                for download_info in download_info_list:
                    codec = getattr(download_info, 'codec', '').lower()
                    # Предпочитаем MP3, но берем любой доступный формат
                    if not best_download_info or codec == 'mp3':
                        best_download_info = download_info
                        if codec == 'mp3':
                            break
                
                if not best_download_info:
                    return None, "Нет подходящих форматов для скачивания"
                
                # Получаем прямую ссылку для скачивания
                direct_link = best_download_info.get_direct_link()
                if not direct_link:
                    return None, "Не удалось получить ссылку для скачивания"
                
                return direct_link, None
                
            except Exception as e:
                logger.warning(f"⚠️ Yandex search error for {artist} - {title}: {e}")
                return None, f"Ошибка поиска: {str(e)}"

        # Ищем трек
        loop = asyncio.get_event_loop()
        mp3_url, search_error = await loop.run_in_executor(None, _sync_search)
        
        if search_error:
            return {
                "success": False, 
                "error": search_error,
                "artist": artist,
                "title": title,
                "search_query": f"{artist} {title}"
            }

        if not mp3_url:
            return {
                "success": False, 
                "error": "Трек не найден в Яндекс.Музыке",
                "artist": artist,
                "title": title,
                "search_query": f"{artist} {title}"
            }

        # Создаем безопасное имя файла
        safe_artist = "".join(c for c in artist if c.isalnum() or c in (' ', '-', '_')).strip()
        safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip()
        filename_safe = f"{safe_artist[:50]} - {safe_title[:50]}.mp3".replace('  ', ' ').replace('__', '_')
        
        downloads_dir = os.path.join(BASE_DIR, "downloads")
        os.makedirs(downloads_dir, exist_ok=True)
        final_path = os.path.join(downloads_dir, filename_safe)

        # Проверяем, не существует ли уже файл (на случай параллельных загрузок)
        if os.path.exists(final_path):
            logger.info(f"📁 Файл уже существует: {filename_safe}")
            # Проверяем, не добавился ли трек в медиатеку параллельно
            if media_library.track_exists(artist, title):
                existing_track = media_library.get_track_by_artist_title(artist, title)
                return {
                    "success": False, 
                    "error": f"Трек уже был добавлен параллельно (ID: {existing_track['id']})",
                    "artist": artist,
                    "title": title,
                    "duplicate": True,
                    "existing_track_id": existing_track['id']
                }
        else:
            # Скачиваем MP3
            async with aiohttp.ClientSession() as session:
                async with session.get(mp3_url, timeout=60) as resp:
                    if resp.status != 200:
                        error_msg = f"Ошибка скачивания: HTTP {resp.status}"
                        if resp.status == 404:
                            error_msg = "Файл не найден на сервере Яндекс.Музыки"
                        elif resp.status == 403:
                            error_msg = "Доступ к треку запрещен"
                        elif resp.status >= 500:
                            error_msg = "Ошибка сервера Яндекс.Музыки"
                            
                        return {
                            "success": False, 
                            "error": error_msg,
                            "artist": artist,
                            "title": title
                        }
                    
                    try:
                        with open(final_path, "wb") as f:
                            async for chunk in resp.content.iter_chunked(8192):
                                f.write(chunk)
                    except IOError as e:
                        return {
                            "success": False, 
                            "error": f"Ошибка записи файла: {str(e)}",
                            "artist": artist,
                            "title": title
                        }

            # Проверяем размер после скачивания
            MAX_SIZE_BYTES = 40 * 1024 * 1024
            if os.path.getsize(final_path) > MAX_SIZE_BYTES:
                os.remove(final_path)
                return {
                    "success": False, 
                    "error": "Файл слишком большой (>40MB)",
                    "artist": artist,
                    "title": title
                }

            # Проверяем, что файл не пустой
            if os.path.getsize(final_path) == 0:
                os.remove(final_path)
                return {
                    "success": False, 
                    "error": "Скачанный файл пустой",
                    "artist": artist,
                    "title": title
                }

        # Добавляем в медиатеку
        result = media_library.add_track(final_path, filename_safe, {
            "artist": artist,
            "title": title,
            "source": "yandex_music"
        })
        
        if not result.get('success'):
            error_msg = result.get('error', 'Неизвестная ошибка добавления в медиатеку')
            if result.get('error') == 'duplicate':
                existing_track = result.get('existing_track')
                return {
                    "success": False, 
                    "error": f"Трек уже существует в медиатеке (ID: {existing_track['id']})",
                    "artist": artist,
                    "title": title,
                    "duplicate": True,
                    "existing_track_id": existing_track['id']
                }
            else:
                return {
                    "success": False, 
                    "error": error_msg,
                    "artist": artist,
                    "title": title
                }

        track = result['track']
        track_id = track["id"]
        
        # Анализ сегмента
        try:
            segment_result = audio_editor.suggest_best_segment(final_path)
            if segment_result is not None:
                media_library.update_track_segment(track_id, segment_result, 30)
                logger.info(f"🎵 Установлен умный отрезок для {artist} - {title}: {segment_result}с")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось установить сегмент для {artist} - {title}: {e}")

        # Поиск фото (опционально)
        try:
            photo_path = image_searcher.fetch_artist_png(artist, track_id)
            if photo_path and os.path.exists(photo_path):
                media_library.update_track(track_id, {"image_path": photo_path})
                logger.info(f"✅ Фото сохранено для: {artist}")
        except Exception as e:
            logger.warning(f"⚠️ Ошибка поиска фото для {artist}: {e}")

        logger.info(f"✅ Успешно обработан: {artist} - {title} (ID: {track_id})")

        return {
            "success": True, 
            "file_path": final_path, 
            "track_id": track_id, 
            "artist": artist,
            "title": title,
            "filename": filename_safe,
            "segment_start": track.get('segment_start', 0)
        }

    except asyncio.TimeoutError:
        logger.error(f"⏰ Таймаут при обработке {artist} - {title}")
        return {
            "success": False, 
            "error": "Таймаут при скачивании трека",
            "artist": artist,
            "title": title
        }
    except aiohttp.ClientError as e:
        logger.error(f"🌐 Ошибка сети при обработке {artist} - {title}: {e}")
        return {
            "success": False, 
            "error": f"Ошибка сети: {str(e)}",
            "artist": artist,
            "title": title
        }
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка при обработке {artist} - {title}: {e}")
        return {
            "success": False, 
            "error": f"Неожиданная ошибка: {str(e)}",
            "artist": artist,
            "title": title
        }

@app.post("/api/tracks/download-from-list")
async def download_tracks_from_list(request_data: dict):
    """Скачивание треков из Яндекс.Музыки по списку названий с улучшенной обработкой ошибок"""
    global download_status
    
    try:
        track_list_text = request_data.get('track_list', '')
        if not track_list_text.strip():
            raise HTTPException(status_code=400, detail="Список треков пуст")
        
        tracks_to_download = parse_track_list(track_list_text)
        if not tracks_to_download:
            raise HTTPException(status_code=400, detail="Не удалось распознать список треков")
        
        logger.info(f"🎵 Начало скачивания {len(tracks_to_download)} треков с Яндекс.Музыки")
        
        # Инициализируем статус скачивания
        download_status.update({
            "is_running": True,
            "total": len(tracks_to_download),
            "current": 0,
            "current_track": "Подготовка к скачиванию...",
            "results": [],
            "failed_tracks": [],
            "duplicate_tracks": [],
            "successful_tracks": []
        })
        
        # Скачиваем треки с обновлением прогресса
        results = []
        for i, track_info in enumerate(tracks_to_download):
            track_name = f"{track_info.get('artist', '')} - {track_info.get('title', '')}".strip(' - ')
            
            # Обновляем статус перед началом скачивания каждого трека
            download_status["current"] = i
            download_status["current_track"] = f"Обработка: {track_name}"
            
            logger.info(f"📊 Прогресс: {i+1}/{len(tracks_to_download)} - {track_name}")
            
            # Скачиваем один трек
            result = await download_single_track(track_info)
            results.append(result)
            
            # Обновляем статус после завершения скачивания
            download_status["current"] = i + 1
            download_status["current_track"] = f"Завершено: {track_name}"
            download_status["results"] = results
            
            # Логируем результат
            if result.get('success'):
                logger.info(f"✅ Успех: {track_name}")
            elif result.get('duplicate'):
                logger.warning(f"🚫 Дубликат: {track_name}")
            else:
                logger.error(f"❌ Ошибка: {track_name} - {result.get('error', 'Неизвестная ошибка')}")
            
            # Небольшая задержка для стабильности и чтобы не нагружать API
            await asyncio.sleep(1)
        
        # Анализируем результаты
        successful_count = len([r for r in results if r.get('success')])
        duplicate_count = len([r for r in results if r.get('duplicate')])
        failed_count = len([r for r in results if not r.get('success') and not r.get('duplicate')])
        
        # Классифицируем результаты для детального отчета
        successful_tracks = [r for r in results if r.get('success')]
        duplicate_tracks = [r for r in results if r.get('duplicate')]
        failed_tracks = [r for r in results if not r.get('success') and not r.get('duplicate')]
        
        # Финальный статус
        download_status.update({
            "is_running": False,
            "current": len(tracks_to_download),
            "current_track": f"Завершено: {successful_count} успешно, {duplicate_count} дубликатов, {failed_count} ошибок",
            "results": results,
            "successful_tracks": successful_tracks,
            "duplicate_tracks": duplicate_tracks,
            "failed_tracks": failed_tracks
        })
        
        logger.info(f"🎉 Скачивание завершено: {successful_count} успешно, {duplicate_count} дубликатов, {failed_count} ошибок")
        
        # Детальный лог ошибок
        if duplicate_tracks:
            logger.info("🚫 Пропущенные дубликаты:")
            for track in duplicate_tracks:
                logger.info(f"   - {track.get('artist')} - {track.get('title')}")
        
        if failed_tracks:
            logger.info("❌ Треки с ошибками:")
            for track in failed_tracks:
                logger.info(f"   - {track.get('artist')} - {track.get('title')}: {track.get('error')}")
        
        return {
            "success": True,
            "message": f"Обработано {len(results)} треков",
            "results": results,
            "downloaded": successful_count,
            "duplicates": duplicate_count,
            "failed": failed_count,
            "source": "yandex_music",
            "statistics": {
                "total": len(tracks_to_download),
                "successful": successful_count,
                "duplicates": duplicate_count,
                "failed": failed_count,
                "success_rate": round((successful_count / len(tracks_to_download)) * 100, 1) if tracks_to_download else 0
            }
        }
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка скачивания треков: {e}")
        download_status.update({
            "is_running": False,
            "current_track": f"Критическая ошибка: {str(e)}"
        })
        raise HTTPException(status_code=500, detail=f"Критическая ошибка скачивания: {str(e)}")

@app.get("/api/download/statistics")
async def get_download_statistics():
    """Получить статистику по последнему скачиванию"""
    try:
        successful_count = len(download_status.get("successful_tracks", []))
        duplicate_count = len(download_status.get("duplicate_tracks", []))
        failed_count = len(download_status.get("failed_tracks", []))
        total = download_status.get("total", 0)
        
        return {
            "success": True,
            "statistics": {
                "total_tracks": total,
                "successful": successful_count,
                "duplicates": duplicate_count,
                "failed": failed_count,
                "success_rate": round((successful_count / total) * 100, 1) if total > 0 else 0,
                "last_update": datetime.now().isoformat()
            },
            "last_download": {
                "is_running": download_status.get("is_running", False),
                "current_track": download_status.get("current_track", ""),
                "total_results": len(download_status.get("results", []))
            }
        }
    except Exception as e:
        logger.error(f"❌ Ошибка получения статистики: {e}")
        return {
            "success": False,
            "error": str(e)
        }

@app.post("/api/download/clear-status")
async def clear_download_status():
    """Очистить статус скачивания"""
    global download_status
    download_status.update({
        "is_running": False,
        "total": 0,
        "current": 0,
        "current_track": "",
        "results": [],
        "failed_tracks": [],
        "duplicate_tracks": [],
        "successful_tracks": []
    })
    return {"success": True, "message": "Статус скачивания очищен"}

# =========================
# PRESENTATION GENERATION API
# =========================

@app.post("/api/generate/presentation")
async def generate_presentation(request_data: dict):
    """Генерация презентации"""
    try:
        logger.info("🎬 Запуск генерации презентации...")
        
        # Проверяем наличие base.pptx
        base_path = os.path.join(BASE_DIR, "base.pptx")
        if not os.path.exists(base_path):
            logger.info("📦 base.pptx не найден, скачиваем из Dropbox...")
            if not dropbox_storage.download_base_pptx(base_path):
                raise HTTPException(status_code=500, detail="Не удалось скачать base.pptx из облака")
        
        # Проверяем наличие треков
        tracks_count = media_library.get_tracks_count()
        if tracks_count < 1:
            raise HTTPException(status_code=400, detail="Недостаточно треков для генерации")
        
        title = request_data.get("title", "Музыкальное Лото")
        make_bw = request_data.get("design", {}).get("make_bw", False)
        
        logger.info(f"📊 Параметры генерации: '{title}', ЧБ: {make_bw}, треков: {tracks_count}")
        
        generator = ModernPresentationGenerator(base_path)
        result_path = generator.generate(
            game_title=title,
            tracks=None,  # автоматически загрузит из tracks.json
            make_bw=make_bw,
            use_parallel=True
        )
        
        # Получаем имя файла для скачивания
        result_dir = Path(result_path)
        pptx_files = list(result_dir.glob("*.pptx"))
        if pptx_files:
            download_filename = pptx_files[0].name
            download_url = f"/api/download/{download_filename}"
            
            logger.info(f"✅ Презентация создана: {download_filename}")
            
            return {
                "success": True,
                "message": "Презентация успешно создана",
                "download_url": download_url,
                "filename": download_filename,
                "path": str(result_path)
            }
        else:
            raise HTTPException(status_code=500, detail="Презентация не была создана")
        
    except FileNotFoundError as e:
        logger.error(f"❌ Файл шаблона не найден: {e}")
        raise HTTPException(status_code=500, detail=f"Шаблон презентации не найден: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка генерации презентации: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка генерации: {str(e)}")

# =========================
# BASIC ROUTES
# =========================

@app.get("/")
async def serve_frontend():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {
        "message": "Music Loto Maker API v3.0 is running",
        "version": "3.0.0",
        "features": [
            "Musical Loto Game",
            "Modern presentations", 
            "Smart metadata parsing",
            "Audio editing",
            "Ticket generation",
            "JSON export",
            "Artist image search",
            "Yandex Music track download",
        ],
    }

# =========================
# TRACK MANAGEMENT API
# =========================
from pydantic import BaseModel

class SegmentUpdate(BaseModel):
    start_time: float
    duration: float = 30
@app.post("/api/tracks/reorder-by-ids")
async def reorder_tracks_by_ids(request: dict):
    """Переупорядочить треки по переданному списку ID и присвоить новые последовательные ID"""
    track_ids = request.get("track_ids")
    if not isinstance(track_ids, list):
        raise HTTPException(status_code=400, detail="track_ids должен быть списком")
    
    # Получаем текущие треки
    current_tracks = {t['id']: t for t in media_library.get_tracks()}
    ordered_tracks = []

    for i, track_id in enumerate(track_ids):
        if track_id not in current_tracks:
            continue
        track = current_tracks[track_id]
        track['id'] = i + 1  # Новый порядковый ID
        ordered_tracks.append(track)

    # Обновляем медиатеку
    media_library.tracks = ordered_tracks
    media_library.save_to_file()
    logger.info(f"🔄 Треки переупорядочены. Новых ID: {len(ordered_tracks)}")
    return {"success": True, "message": f"Переупорядочено {len(ordered_tracks)} треков"}
@app.put("/api/tracks/{track_id}/change-id")
async def change_track_id_endpoint(track_id: int, request: IDChangeRequest):
    """Изменить ID трека. new_id должен быть свободен."""
    if media_library.get_track(request.new_id):
        raise HTTPException(status_code=400, detail="ID уже занят")
    if media_library.change_track_id(track_id, request.new_id):
        return {"success": True, "message": f"ID изменён: {track_id} → {request.new_id}"}
    raise HTTPException(status_code=404, detail="Трек не найден")

@app.put("/api/tracks/swap-ids")
async def swap_track_ids_endpoint(request: IDSwapRequest):
    """Поменять местами ID двух треков."""
    if media_library.swap_track_ids(request.track1_id, request.track2_id):
        return {
            "success": True,
            "message": f"ID поменяны местами: {request.track1_id} ↔ {request.track2_id}"
        }
    raise HTTPException(status_code=404, detail="Один из треков не найден")

@app.post("/api/tracks/compact")
async def compact_track_ids_endpoint():
    """Уплотнить ID треков (1, 2, 3, ..., N)."""
    if media_library.compact_ids():
        return {"success": True, "message": "ID успешно уплотнены"}
    return {"success": False, "message": "Не удалось уплотнить ID"}
@app.put("/api/tracks/{track_id}/segment")
async def update_track_segment_endpoint(track_id: int, update: SegmentUpdate):
    """Обновить отрезок трека (начало и длительность)"""
    track = media_library.get_track(track_id)
    if not track:
        raise HTTPException(status_code=404, detail="Трек не найден")

    success = media_library.update_track_segment(
        track_id=track_id,
        start_time=update.start_time,
        duration=update.duration
    )
    if not success:
        raise HTTPException(status_code=500, detail="Не удалось обновить отрезок")

    logger.info(f"🔄 Отрезок трека {track_id} обновлён: {update.start_time}с, {update.duration}с")
    return {"success": True, "message": "Отрезок успешно сохранён"}
@app.get("/api/tracks")
async def get_tracks():
    """Возвращает список треков из медиатеки"""
    try:
        tracks = media_library.get_tracks()
        logger.info(f"📊 Запрошены треки, найдено: {len(tracks)}")
        return tracks
    except Exception as e:
        logger.error(f"❌ Ошибка получения треков: {e}")
        return []

@app.get("/api/tracks/count")
async def get_tracks_count():
    """Возвращает количество треков"""
    try:
        count = media_library.get_tracks_count()
        return {"count": count, "status": "sufficient" if count >= 40 else "insufficient"}
    except Exception as e:
        logger.error(f"❌ Ошибка получения количества треков: {e}")
        return {"count": 0, "status": "error"}

@app.post("/api/tracks/upload")
async def upload_tracks(files: list[UploadFile] = File(...)):
    """Загрузка треков с локального компьютера с проверкой дубликатов"""
    MAX_SIZE_MB = 40
    MAX_SIZE_BYTES = MAX_SIZE_MB * 1024 * 1024
    ALLOWED_EXTENSIONS = {'.mp3', '.wav', '.flac', '.m4a', '.aac'}

    saved_tracks, errors, duplicates = [], [], []
    logger.info(f"📤 Начало загрузки {len(files)} файлов")

    for file in files:
        try:
            logger.info(f"🔍 Обработка файла: {file.filename}")
            file_extension = Path(file.filename).suffix.lower()

            if file_extension not in ALLOWED_EXTENSIONS:
                msg = f"Неподдерживаемый формат: {file_extension}"
                errors.append(msg)
                logger.warning(f"⚠️ {msg}")
                continue

            file.file.seek(0, os.SEEK_END)
            file_size = file.file.tell()
            file.file.seek(0)
            if file_size > MAX_SIZE_BYTES:
                msg = f"Файл {file.filename} превышает лимит {MAX_SIZE_MB} МБ"
                errors.append(msg)
                logger.warning(f"⚠️ {msg}")
                continue

            # Парсим метаданные для проверки дубликата
            metadata = metadata_processor.process(file.filename)
            cleaned_artist = re.sub(r'\s*\([^)]*\)$', '', metadata.get('artist', 'Неизвестный исполнитель')).strip()
            cleaned_title = re.sub(r'\s*\([^)]*\)$', '', metadata.get('title', 'Без названия')).strip()

            # ПРОВЕРКА ДУБЛИКАТА
            if media_library.track_exists(cleaned_artist, cleaned_title):
                duplicate_msg = f"Дубликат: {cleaned_artist} - {cleaned_title}"
                duplicates.append(duplicate_msg)
                logger.warning(f"🚫 {duplicate_msg}")
                continue

            downloads_dir = os.path.join(BASE_DIR, "downloads")
            os.makedirs(downloads_dir, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_filename = f"{timestamp}_{Path(file.filename).stem.replace(' ', '_')}{file_extension}"
            file_path = os.path.join(downloads_dir, safe_filename)

            with open(file_path, "wb") as buffer:
                content = await file.read()
                buffer.write(content)

            if not os.path.exists(file_path):
                msg = f"Файл не сохранён: {file_path}"
                errors.append(msg)
                logger.error(f"❌ {msg}")
                continue

            # Добавляем трек в медиатеку
            result = media_library.add_track(file_path, file.filename, metadata)
            if not result.get('success'):
                if result.get('error') == 'duplicate':
                    duplicate_msg = f"Дубликат при добавлении: {cleaned_artist} - {cleaned_title}"
                    duplicates.append(duplicate_msg)
                    logger.warning(f"🚫 {duplicate_msg}")
                else:
                    msg = f"Не удалось добавить трек в медиатеку: {file.filename}"
                    errors.append(msg)
                    logger.error(f"❌ {msg}")
                continue

            track = result['track']

            try:
                best_start = audio_editor.suggest_best_segment(file_path)
                media_library.update_track_segment(track['id'], best_start, 30)
            except Exception as e:
                logger.warning(f"⚠️ Не удалось установить умный отрезок: {e}")

            try:
                logger.info(f"🖼️ Поиск фото для артиста: {cleaned_artist}")
                photo_path = image_searcher.fetch_artist_png(cleaned_artist, track['id'])
                if photo_path and os.path.exists(photo_path):
                    logger.info(f"✅ Фото артиста сохранено: {photo_path}")
                    media_library.update_track(track['id'], {'image_path': photo_path})
                    track['image_path'] = photo_path
                else:
                    logger.warning(f"⚠️ Фото для {cleaned_artist} не найдено")
            except Exception as e:
                logger.warning(f"⚠️ Ошибка при поиске фото артиста {cleaned_artist}: {e}")

            saved_tracks.append(track)

        except Exception as e:
            msg = f"Ошибка загрузки {file.filename}: {str(e)}"
            errors.append(msg)
            logger.error(f"❌ {msg}", exc_info=True)

    response_message = f"Успешно загружено {len(saved_tracks)} треков"
    if duplicates:
        response_message += f", пропущено дубликатов: {len(duplicates)}"
    if errors:
        response_message += f", ошибок: {len(errors)}"
        
    logger.info(f"📊 Итог загрузки: {response_message}")

    return {
        "message": response_message, 
        "tracks": saved_tracks, 
        "errors": errors,
        "duplicates": duplicates
    }

@app.put("/api/tracks/{track_id}")
async def update_track(track_id: int, track_data: dict):
    try:
        success = media_library.update_track(track_id, track_data)
        if success:
            return {"message": "Трек обновлен"}
        raise HTTPException(status_code=404, detail="Трек не найден")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка обновления: {str(e)}")

@app.delete("/api/tracks/{track_id}")
async def delete_track(track_id: int):
    try:
        result = media_library.delete_track(track_id)
        if result.get('success'):
            return {"message": "Трек удален", "files_removed": result.get('files_removed', [])}
        raise HTTPException(status_code=404, detail="Трек не найден")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка удаления: {str(e)}")

@app.delete("/api/tracks")
async def clear_tracks():
    try:
        result = media_library.clear()
        if result.get('success'):
            return {
                "message": "Медиатека очищена", 
                "tracks_deleted": result.get('tracks_deleted', 0),
                "files_removed": result.get('files_removed', [])
            }
        raise HTTPException(status_code=500, detail="Ошибка очистки медиатеки")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка очистки: {str(e)}")

# =========================
# DUPLICATE CHECKING API
# =========================

@app.post("/api/tracks/check-duplicate")
async def check_track_duplicate(request_data: dict):
    """Проверить, есть ли трек в медиатеке"""
    try:
        artist = request_data.get('artist', '').strip()
        title = request_data.get('title', '').strip()
        
        if not artist or not title:
            return {"is_duplicate": False, "error": "Не указаны артист или название"}
        
        is_duplicate = media_library.track_exists(artist, title)
        duplicates = media_library.find_duplicate_tracks(artist, title) if is_duplicate else []
        
        return {
            "is_duplicate": is_duplicate,
            "artist": artist,
            "title": title,
            "existing_tracks": duplicates
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка проверки дубликата: {e}")
        return {"is_duplicate": False, "error": str(e)}

@app.get("/api/tracks/duplicates")
async def get_all_duplicates():
    """Получить все дубликаты в медиатеке"""
    try:
        tracks = media_library.get_tracks()
        seen = {}
        duplicates = []
        
        for track in tracks:
            key = f"{normalize_track_string(track['artist'])}|{normalize_track_string(track['title'])}"
            if key in seen:
                duplicates.append({
                    'artist': track['artist'],
                    'title': track['title'],
                    'tracks': [seen[key], track]
                })
            else:
                seen[key] = track
        
        return {
            "duplicates": duplicates,
            "total_duplicate_groups": len(duplicates)
        }
    except Exception as e:
        logger.error(f"❌ Ошибка поиска дубликатов: {e}")
        return {"duplicates": [], "error": str(e)}

@app.get("/api/tracks/duplicates/detailed")
async def get_detailed_duplicates():
    """Получить детальную информацию о дубликатах"""
    try:
        tracks = media_library.get_tracks()
        seen = {}
        duplicates = []
        
        for track in tracks:
            key = f"{normalize_track_string(track['artist'])}|{normalize_track_string(track['title'])}"
            if key in seen:
                # Нашли дубликат
                original_track = seen[key]
                duplicate_info = {
                    'artist': track['artist'],
                    'title': track['title'],
                    'tracks': [
                        {
                            'id': original_track['id'],
                            'file_path': original_track['file_path'],
                            'original_filename': original_track['original_filename'],
                            'created_at': original_track.get('created_at', ''),
                            'image_path': original_track.get('image_path')
                        },
                        {
                            'id': track['id'],
                            'file_path': track['file_path'],
                            'original_filename': track['original_filename'],
                            'created_at': track.get('created_at', ''),
                            'image_path': track.get('image_path')
                        }
                    ]
                }
                duplicates.append(duplicate_info)
            else:
                seen[key] = track
        
        return {
            "duplicates": duplicates,
            "total_duplicate_groups": len(duplicates),
            "total_duplicate_tracks": sum(len(group['tracks']) for group in duplicates)
        }
    except Exception as e:
        logger.error(f"❌ Ошибка поиска дубликатов: {e}")
        return {"duplicates": [], "error": str(e)}

# =========================
# ARTIST PHOTOS API
# =========================

@app.get("/api/tracks/{track_id}/artist-photo")
async def get_artist_photo(track_id: int):
    """Получить фото артиста для трека"""
    try:
        track = media_library.get_track(track_id)
        if not track:
            raise HTTPException(status_code=404, detail="Трек не найден")

        image_path = track.get('image_path')
        
        # Если путь есть и файл существует - возвращаем фото
        if image_path and os.path.exists(image_path):
            logger.info(f"✅ Отдаем фото для трека {track_id}: {image_path}")
            return FileResponse(
                image_path,
                media_type='image/png',
                filename=f"artist_{track_id}.png"
            )
        
        # Если фото нет, возвращаем 404
        logger.warning(f"⚠️ Фото не найдено для трека {track_id}")
        raise HTTPException(status_code=404, detail="Фото артиста не найдено")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка получения фото для трека {track_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка получения фото: {str(e)}")

@app.post("/api/tracks/{track_id}/search-artist-photo")
async def search_artist_photo(track_id: int, request_data: dict):
    try:
        track = media_library.get_track(track_id)
        if not track:
            raise HTTPException(status_code=404, detail="Трек не найден")
        artist_name = request_data.get('artist', track.get('artist', ''))
        get_multiple = request_data.get('get_multiple', True)
        if not artist_name:
            raise HTTPException(status_code=400, detail="Имя артиста не указано")
        if get_multiple:
            photo_urls = image_searcher.fetch_multiple_artist_photos(artist_name, count=10)
        else:
            single_photo_path = image_searcher.fetch_artist_png(artist_name, track_id)
            photo_urls = [single_photo_path] if single_photo_path else []

        if photo_urls:
            return {"success": True, "message": f"Найдено {len(photo_urls)} фото",
                    "photos": photo_urls, "artist": artist_name, "count": len(photo_urls)}
        return {"success": False, "message": "Не удалось найти фото артиста"}
    except Exception as e:
        logger.error(f"❌ Ошибка поиска фото: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка поиска фото: {str(e)}")

@app.post("/api/tracks/{track_id}/upload-artist-photo")
async def upload_artist_photo(track_id: int, photo: UploadFile = File(...)):
    """Загрузить фото артиста для конкретного трека"""
    try:
        track = media_library.get_track(track_id)
        if not track:
            raise HTTPException(status_code=404, detail="Трек не найден")

        if not photo.content_type or not photo.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="Файл должен быть изображением")

        # Создаем папку для изображений если нет
        images_dir = os.path.join(BASE_DIR, "images")
        os.makedirs(images_dir, exist_ok=True)

        # Генерируем имя файла
        file_extension = Path(photo.filename).suffix.lower()
        image_filename = f"{track_id}_artist{file_extension}"
        image_path = os.path.join(images_dir, image_filename)

        # Сохраняем файл
        content = await photo.read()
        if not content:
            raise HTTPException(status_code=400, detail="Файл пустой")

        with open(image_path, "wb") as f:
            f.write(content)

        # Обновляем трек с новым путем к фото
        media_library.update_track(track_id, {'image_path': image_path})

        logger.info(f"✅ Фото артиста загружено для трека {track_id}: {image_path}")

        return {
            "success": True,
            "message": "Фото артиста успешно загружено",
            "image_path": image_path,
            "artist": track.get('artist', '')
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки фото артиста: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка загрузки фото: {str(e)}")

@app.post("/api/tracks/{track_id}/save-artist-photo")
async def save_artist_photo(track_id: int, request_data: dict):
    try:
        track = media_library.get_track(track_id)
        if not track:
            raise HTTPException(status_code=404, detail="Трек не найден")
        photo_url = request_data.get('photo_url')
        artist_name = request_data.get('artist', track.get('artist', ''))
        if not photo_url:
            raise HTTPException(status_code=400, detail="URL фото не указан")
        
        # Скачиваем и сохраняем фото
        images_dir = os.path.join(BASE_DIR, "images")
        os.makedirs(images_dir, exist_ok=True)
        
        image_path = os.path.join(images_dir, f"{track_id}_artist.png")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(photo_url) as response:
                if response.status == 200:
                    with open(image_path, 'wb') as f:
                        f.write(await response.read())
        
        if os.path.exists(image_path):
            media_library.update_track(track_id, {'image_path': image_path, 'artist': artist_name})
            return {"success": True, "message": "Фото артиста сохранено",
                    "image_path": image_path, "artist": artist_name}
        raise HTTPException(status_code=500, detail="Не удалось сохранить фото")
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения фото: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка сохранения фото: {str(e)}")

# =========================
# AUDIO EDITOR API
# =========================

@app.get("/api/tracks/{track_id}/waveform")
async def get_track_waveform(track_id: int):
    try:
        track = media_library.get_track(track_id)
        if not track:
            raise HTTPException(status_code=404, detail="Track not found")
        
        # Генерируем waveform
        waveform_data = audio_editor.generate_waveform(track['file_path'])
        if waveform_data:
            return {"waveform_data": waveform_data}
        else:
            raise HTTPException(status_code=500, detail="Failed to generate waveform")
    except Exception as e:
        logger.error(f"❌ Ошибка генерации waveform: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка генерации waveform: {str(e)}")

@app.post("/api/tracks/{track_id}/play")
async def play_track_segment(track_id: int, play_data: dict = None):
    try:
        start_time = play_data.get('start_time', 0) if play_data else 0
        duration = play_data.get('duration', 30) if play_data else 30
        track = media_library.get_track(track_id)
        if not track:
            raise HTTPException(status_code=404, detail="Track not found")
        success = audio_editor.play_segment(track['file_path'], start_time, duration)
        if success:
            return {"success": True, "message": "Playback started"}
        return {"success": False, "message": "Playback failed"}
    except Exception as e:
        logger.error(f"❌ Ошибка воспроизведения: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка воспроизведения: {str(e)}")

@app.post("/api/tracks/stop")
async def stop_playback():
    try:
        audio_editor.stop_playback()
        return {"success": True, "message": "Playback stopped"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка остановки: {str(e)}")

@app.get("/api/tracks/{track_id}/suggest-segment")
async def suggest_best_segment(track_id: int):
    try:
        track = media_library.get_track(track_id)
        if not track:
            raise HTTPException(status_code=404, detail="Track not found")
        best_start = audio_editor.suggest_best_segment(track['file_path'])
        return {"success": True, "suggested_start": best_start}
    except Exception as e:
        logger.error(f"❌ Ошибка анализа отрезка: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка анализа: {str(e)}")

@app.get("/api/tracks/{track_id}/segment-file")
async def get_track_segment_file(track_id: int, start_time: float = 0, duration: float = 30):
    try:
        track = media_library.get_track(track_id)
        if not track:
            raise HTTPException(status_code=404, detail="Track not found")
        
        segment_start = start_time if start_time > 0 else track.get('segment_start', 0)
        segment_duration = duration if duration > 0 else track.get('segment_duration', 30)
        
        segment_filename = f"preview_{track_id}_{int(segment_start)}s.mp3"
        segment_path = os.path.join(BASE_DIR, "temp", segment_filename)
        os.makedirs(os.path.dirname(segment_path), exist_ok=True)
        
        segment_path = audio_editor.extract_segment(
            track['file_path'], segment_start, segment_duration, segment_path
        )
        
        if segment_path and os.path.exists(segment_path):
            return FileResponse(segment_path,
                                filename=f"preview_{track['artist']}_{track['title']}.mp3",
                                media_type='audio/mpeg')
        raise HTTPException(status_code=500, detail="Failed to create preview segment")
    except Exception as e:
        logger.error(f"❌ Ошибка создания предпросмотра отрезка: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# =========================
# LOCAL FILES MANAGEMENT
# =========================

@app.delete("/api/local/artist-photo/{filename}")
async def delete_local_artist_photo(filename: str):
    """Удалить фото артиста"""
    try:
        artists_dir = os.path.join(BASE_DIR, "artists")
        file_path = os.path.join(artists_dir, filename)
        
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="Фото не найдено")
        
        os.remove(file_path)
        logger.info(f"🗑️ Удалено фото: {filename}")
        
        return {"success": True, "message": "Фото удалено"}
        
    except Exception as e:
        logger.error(f"❌ Ошибка удаления фото: {e}")
        return {"success": False, "error": str(e)}

@app.get("/api/local/artist-photos")
async def get_local_artist_photos():
    """Получить список локальных фото артистов"""
    try:
        artists_dir = os.path.join(BASE_DIR, "artists")
        photos = []
        
        if os.path.exists(artists_dir):
            for filename in os.listdir(artists_dir):
                if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                    file_path = os.path.join(artists_dir, filename)
                    file_size = os.path.getsize(file_path)
                    artist_name = os.path.splitext(filename)[0].replace('_', ' ')
                    photos.append({
                        "filename": filename,
                        "artist_name": artist_name,
                        "file_path": file_path,
                        "size": file_size,
                        "url": f"/api/local/artist-photo/{filename}",
                        "size_mb": f"{(file_size / 1024 / 1024):.2f} MB"
                    })
        
        logger.info(f"📁 Найдено {len(photos)} локальных фото артистов")
        return {"photos": sorted(photos, key=lambda x: x['artist_name'])}
    except Exception as e:
        logger.error(f"❌ Ошибка получения локальных фото: {e}")
        return {"photos": []}

@app.get("/api/local/artist-photo/{filename}")
async def get_local_artist_photo(filename: str):
    """Получить локальное фото артиста"""
    try:
        artists_dir = os.path.join(BASE_DIR, "artists")
        file_path = os.path.join(artists_dir, filename)
        
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="Фото не найдено")
        
        # Определяем MIME тип по расширению
        ext = filename.lower().split('.')[-1]
        mime_types = {
            'png': 'image/png',
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg',
            'webp': 'image/webp'
        }
        media_type = mime_types.get(ext, 'image/jpeg')
        
        return FileResponse(file_path, media_type=media_type)
    except Exception as e:
        logger.error(f"❌ Ошибка получения фото {filename}: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка получения фото: {str(e)}")

@app.post("/api/local/upload-artist-photos")
async def upload_local_artist_photos(files: List[UploadFile] = File(...)):
    """Загрузить фото артистов в локальную папку"""
    try:
        artists_dir = os.path.join(BASE_DIR, "artists")
        os.makedirs(artists_dir, exist_ok=True)
        
        uploaded = []
        total_size = 0
        
        for file in files:
            logger.info(f"🔼 Обработка файла: {file.filename}")
            
            if not file.filename:
                continue
                
            if not file.content_type or not file.content_type.startswith('image/'):
                logger.warning(f"⚠️ Пропущен не-изображение: {file.filename}")
                continue
            
            # Создаем безопасное имя файла
            safe_name = "".join(c for c in file.filename if c.isalnum() or c in (' ', '-', '_', '.')).rstrip()
            safe_name = safe_name.replace(' ', '_').lower()
            
            # Добавляем расширение если его нет
            if not '.' in safe_name:
                safe_name += '.jpg'
            
            file_path = os.path.join(artists_dir, safe_name)
            
            # Читаем и сохраняем файл
            content = await file.read()
            if not content:
                logger.warning(f"⚠️ Пустой файл: {file.filename}")
                continue
                
            with open(file_path, "wb") as f:
                f.write(content)
            
            # Проверяем что файл сохранился
            if os.path.exists(file_path):
                file_size = os.path.getsize(file_path)
                total_size += file_size
                uploaded.append({
                    "filename": safe_name,
                    "artist_name": os.path.splitext(safe_name)[0].replace('_', ' '),
                    "file_path": file_path,
                    "size": file_size
                })
                logger.info(f"✅ Фото сохранено: {safe_name} ({file_size} байт)")
            else:
                logger.error(f"❌ Файл не сохранился: {safe_name}")
        
        logger.info(f"📊 Итог загрузки: {len(uploaded)} из {len(files)} файлов, общий размер: {total_size} байт")
        
        return {
            "success": True, 
            "uploaded": uploaded, 
            "message": f"Успешно загружено {len(uploaded)} фото",
            "total_files": len(files),
            "total_size": total_size
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки фото: {e}")
        return {"success": False, "error": str(e)}

@app.get("/api/local/base-pptx")
async def get_base_pptx_info():
    """Получить информацию о base.pptx"""
    try:
        base_path = os.path.join(BASE_DIR, "base.pptx")
        
        if os.path.exists(base_path):
            file_size = os.path.getsize(base_path)
            return {
                "exists": True,
                "filename": "base.pptx",
                "size": file_size,
                "download_url": "/api/local/download-base-pptx",
                "message": "Файл готов к использованию"
            }
        else:
            return {
                "exists": False, 
                "message": "base.pptx не найден",
                "download_url": "/api/dropbox/download-base-pptx"
            }
            
    except Exception as e:
        logger.error(f"❌ Ошибка получения информации о base.pptx: {e}")
        return {"exists": False, "error": str(e)}

@app.get("/api/local/download-base-pptx")
async def download_base_pptx():
    """Скачать base.pptx"""
    try:
        base_path = os.path.join(BASE_DIR, "base.pptx")
        
        if not os.path.exists(base_path):
            raise HTTPException(status_code=404, detail="base.pptx не найден")
        
        return FileResponse(
            base_path,
            filename="base.pptx",
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation"
        )
    except Exception as e:
        logger.error(f"❌ Ошибка скачивания base.pptx: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка скачивания: {str(e)}")

@app.post("/api/local/upload-base-pptx")
async def upload_base_pptx(file: UploadFile = File(...)):
    """Загрузить новый base.pptx"""
    try:
        logger.info(f"🔼 Начало загрузки base.pptx: {file.filename}")
        
        if not file.filename or not file.filename.endswith('.pptx'):
            raise HTTPException(status_code=400, detail="Файл должен быть в формате .pptx")
        
        base_path = os.path.join(BASE_DIR, "base.pptx")
        
        # Читаем содержимое файла
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Файл пустой")
        
        logger.info(f"📊 Размер файла: {len(content)} байт")
        
        # Сохраняем файл
        with open(base_path, "wb") as f:
            f.write(content)
        
        # Проверяем что файл сохранился
        if not os.path.exists(base_path):
            raise HTTPException(status_code=500, detail="Файл не сохранился на сервере")
        
        file_size = os.path.getsize(base_path)
        logger.info(f"✅ base.pptx обновлен, размер: {file_size} байт")
        
        return {
            "success": True,
            "message": "base.pptx успешно обновлен",
            "size": file_size,
            "filename": "base.pptx"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки base.pptx: {e}")
        return {"success": False, "error": str(e)}

# =========================
# HEALTH AND STATUS
# =========================

@app.get("/api/status")
async def get_status():
    try:
        tracks_count = media_library.get_tracks_count()
        tracks_with_photos = len([t for t in media_library.get_tracks() if t.get("image_path") and os.path.exists(t.get("image_path"))])
        
        # Проверяем дубликаты
        duplicates_result = await get_all_duplicates()
        duplicate_groups = duplicates_result.get('total_duplicate_groups', 0)
        
        status_info = {
            "status": "running",
            "version": "3.0.0",
            "tracks_count": tracks_count,
            "tracks_with_photos": tracks_with_photos,
            "duplicate_groups": duplicate_groups,
            "musical_loto_ready": tracks_count >= 40 and duplicate_groups == 0,
            "metadata_processor": type(metadata_processor).__name__,
            "features": [
                "musical_loto_game",
                "modern_presentations",
                "smart_metadata",
                "audio_editing",
                "ticket_generation",
                "json_export",
                "artist_images_manual",
                "yandex_music_track_download",
                "duplicate_checking"
            ],
        }
        
        if tracks_count < 40:
            status_info["warning"] = f"Для Musical Loto нужно ещё {40 - tracks_count} треков"
        elif duplicate_groups > 0:
            status_info["warning"] = f"Найдено {duplicate_groups} групп дубликатов"
        else:
            status_info["message"] = "Musical Loto готов к генерации!"
            
        return status_info
    except Exception as e:
        logger.error(f"❌ Ошибка статуса: {e}")
        return {"status": "error", "version": "3.0.0", "tracks_count": 0, "error": str(e)}

@app.get("/api/health")
async def health_check():
    tracks_count = media_library.get_tracks_count()
    tracks_with_photos = len([t for t in media_library.get_tracks() if t.get('image_path') and os.path.exists(t.get('image_path'))])
    return {
        "status": "healthy",
        "service": "Music Loto Maker API v3.0",
        "timestamp": datetime.now().isoformat(),
        "tracks_loaded": tracks_count,
        "tracks_with_photos": tracks_with_photos,
        "musical_loto_ready": tracks_count >= 40,
        "features": [
            "musical_loto",
            "modern_presentations",
            "smart_metadata",
            "audio_editing",
            "ticket_generation",
            "json_export",
            "artist_images_manual",
            "yandex_music_track_download",
            "duplicate_checking"
        ],
    }

# =========================
# FILE DOWNLOAD
# =========================

@app.get("/api/download/{filename}")
async def download_file(filename: str):
    """Скачивание файлов из различных директорий проекта"""
    try:
        logger.info(f"📥 Запрос на скачивание файла: {filename}")
        
        if not filename or '..' in filename or filename.startswith('/'):
            logger.warning(f"🚫 Некорректное имя файла: {filename}")
            raise HTTPException(status_code=400, detail="Некорректное имя файла")
        
        filename = filename.split('?')[0]
        
        possible_paths = [
            os.path.join(BASE_DIR, "output", filename),
            os.path.join(BASE_DIR, "assets", "custom_buttons", filename),
            os.path.join(BASE_DIR, "assets", "backgrounds", filename),
            os.path.join(BASE_DIR, "downloads", filename),
            os.path.join(BASE_DIR, "uploads", filename),
            os.path.join(BASE_DIR, "temp", filename),
            os.path.join(BASE_DIR, "images", filename),
            os.path.join(BASE_DIR, filename),
        ]
        
        output_dir = os.path.join(BASE_DIR, "output")
        if os.path.exists(output_dir):
            for root, dirs, files in os.walk(output_dir):
                for file in files:
                    if file == filename:
                        possible_paths.append(os.path.join(root, file))
        
        logger.info(f"🔍 Ищем файл по путям: {[p for p in possible_paths if 'output' in p]}")
        
        file_path = None
        for path in possible_paths:
            if os.path.exists(path) and os.path.isfile(path):
                file_path = path
                logger.info(f"✅ Файл найден: {file_path}")
                break
        
        if not file_path:
            output_dir = os.path.join(BASE_DIR, "output")
            if os.path.exists(output_dir):
                for root, dirs, files in os.walk(output_dir):
                    for file in files:
                        if file.lower() == filename.lower():
                            file_path = os.path.join(root, file)
                            logger.info(f"✅ Файл найден (без учета регистра): {file_path}")
                            break
                    if file_path:
                        break
        
        if not file_path:
            logger.warning(f"❌ Файл не найден: {filename}")
            logger.warning(f"📁 Содержимое output директории: {os.listdir(os.path.join(BASE_DIR, 'output')) if os.path.exists(os.path.join(BASE_DIR, 'output')) else 'Директория не существует'}")
            raise HTTPException(status_code=404, detail=f"Файл '{filename}' не найден")

        file_size = os.path.getsize(file_path)
        if file_size == 0:
            logger.warning(f"⚠️ Файл пустой: {file_path}")
            raise HTTPException(status_code=500, detail="Файл пустой")

        file_ext = os.path.splitext(filename)[1].lower()
        mime_types = {
            '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            '.zip': 'application/zip',
            '.mp3': 'audio/mpeg',
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.json': 'application/json',
            '.txt': 'text/plain'
        }
        
        media_type = mime_types.get(file_ext, 'application/octet-stream')
        
        logger.info(f"📤 Отправляем файл: {filename} ({file_size} bytes, {media_type})")
        
        return FileResponse(
            file_path, 
            filename=filename, 
            media_type=media_type,
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Content-Length': str(file_size)
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Критическая ошибка при загрузке файла {filename}: {e}")
        logger.exception("Полная трассировка ошибки:")
        raise HTTPException(status_code=500, detail=f"Внутренняя ошибка сервера: {str(e)}")
# =========================
# IMPORT/EXPORT SYSTEM (LOW RAM USAGE)
# =========================

import zipfile
import shutil
from pathlib import Path

@app.get("/api/export/all-data")
async def export_all_data():
    """Экспорт всех данных в ZIP архив (максимум 100MB RAM)"""
    try:
        logger.info("📦 Начало экспорта всех данных (LOW RAM mode)...")
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_filename = f"music_loto_export_{timestamp}.zip"
        zip_path = os.path.join(BASE_DIR, "temp", zip_filename)
        
        # ОЧЕНЬ АГРЕССИВНАЯ ОПТИМИЗАЦИЯ ПАМЯТИ
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=1) as zipf:
            # 1. track_data.json (маленький файл)
            track_data_path = os.path.join(BASE_DIR, "track_data.json")
            if os.path.exists(track_data_path):
                zipf.write(track_data_path, "track_data.json")
                logger.info("✅ track_data.json добавлен")
            
            # 2. Папка images - ОЧЕНЬ экономно
            images_dir = os.path.join(BASE_DIR, "images")
            if os.path.exists(images_dir):
                image_files = []
                for root, dirs, files in os.walk(images_dir):
                    for file in files:
                        if file.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                            image_files.append(os.path.join(root, file))
                
                # Обрабатываем по 10 файлов за раз
                for i, file_path in enumerate(image_files):
                    if i % 10 == 0 and i > 0:
                        logger.info(f"🖼️ Обработано {i}/{len(image_files)} изображений")
                        import gc
                        gc.collect()  # Принудительная очистка памяти
                    
                    arcname = os.path.join("images", os.path.relpath(file_path, images_dir))
                    zipf.write(file_path, arcname)
                
                logger.info(f"✅ Изображений добавлено: {len(image_files)}")
            
            # 3. Папка downloads - САМАЯ ЭКОНОМНАЯ ОБРАБОТКА
            downloads_dir = os.path.join(BASE_DIR, "downloads")
            if os.path.exists(downloads_dir):
                # Получаем список файлов БЕЗ загрузки в память
                audio_files = []
                total_size = 0
                
                for root, dirs, files in os.walk(downloads_dir):
                    for file in files:
                        if file.lower().endswith(('.mp3', '.wav', '.flac', '.m4a', '.aac')):
                            file_path = os.path.join(root, file)
                            file_size = os.path.getsize(file_path)
                            
                            # ФИЛЬТР: пропускаем очень большие файлы (>50MB)
                            if file_size > 50 * 1024 * 1024:
                                logger.warning(f"⚠️ Пропущен большой файл: {file} ({file_size/1024/1024:.1f}MB)")
                                continue
                                
                            audio_files.append((file_path, file_size))
                            total_size += file_size
                
                logger.info(f"🎵 Найдено {len(audio_files)} аудиофайлов (~{total_size/1024/1024:.1f}MB)")
                
                # Обрабатываем по 5 файлов за раз для экономии RAM
                processed = 0
                skipped_due_to_size = 0
                
                for i, (file_path, file_size) in enumerate(audio_files):
                    # ДОПОЛНИТЕЛЬНАЯ ПРОВЕРКА РАЗМЕРА
                    if file_size > 30 * 1024 * 1024:  # >30MB
                        skipped_due_to_size += 1
                        continue
                    
                    if processed % 5 == 0 and processed > 0:
                        logger.info(f"🎵 Добавлено {processed}/{len(audio_files)} аудиофайлов")
                        import gc
                        gc.collect()  # Жесткая очистка памяти
                    
                    try:
                        arcname = os.path.join("downloads", os.path.relpath(file_path, downloads_dir))
                        zipf.write(file_path, arcname)
                        processed += 1
                    except Exception as e:
                        logger.error(f"❌ Ошибка добавления {file_path}: {e}")
                        continue
                
                logger.info(f"✅ Аудиофайлов добавлено: {processed}, пропущено: {skipped_due_to_size}")
        
        final_size = os.path.getsize(zip_path)
        logger.info(f"✅ Экспорт завершен: {zip_filename} ({final_size / 1024 / 1024:.2f} MB)")
        
        # Получаем актуальные данные для ответа
        tracks_count = media_library.get_tracks_count()
        images_count = len([f for f in os.listdir(images_dir) if os.path.isfile(os.path.join(images_dir, f))]) if os.path.exists(images_dir) else 0
        downloads_count = len([f for f in os.listdir(downloads_dir) if os.path.isfile(os.path.join(downloads_dir, f))]) if os.path.exists(downloads_dir) else 0
        
        return {
            "success": True,
            "message": "Экспорт данных завершен",
            "filename": zip_filename,
            "download_url": f"/api/download/{zip_filename}",
            "size": final_size,
            "info": {
                "tracks_count": tracks_count,
                "images_count": images_count,
                "downloads_count": downloads_count,
                "estimated_size_mb": round(final_size / 1024 / 1024, 2)
            }
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка экспорта данных: {e}")
        return {"success": False, "error": str(e)}

@app.post("/api/import/all-data")
async def import_all_data(file: UploadFile = File(...)):
    """Импорт данных из ZIP архива (максимум 100MB RAM)"""
    try:
        logger.info(f"📥 Начало импорта (LOW RAM mode)...")
        
        if not file.filename.endswith('.zip'):
            raise HTTPException(status_code=400, detail="Файл должен быть в формате ZIP")
        
        # СОЗДАЕМ ВРЕМЕННУЮ ПАПКУ
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        import_dir = os.path.join(BASE_DIR, "temp", f"import_{timestamp}")
        os.makedirs(import_dir, exist_ok=True)
        
        zip_path = os.path.join(import_dir, file.filename)
        
        # ЗАПИСЫВАЕМ ФАЙЛ ЧАНКАМИ (не загружаем весь файл в RAM)
        with open(zip_path, "wb") as f:
            # Читаем файл частями по 1MB
            while True:
                chunk = await file.read(1024 * 1024)  # 1MB chunks
                if not chunk:
                    break
                f.write(chunk)
        
        logger.info("✅ Файл сохранен, начинаем распаковку...")
        
        # РАСПАКОВКА С КОНТРОЛЕМ ПАМЯТИ
        imported_items = []
        
        with zipfile.ZipFile(zip_path, 'r') as zipf:
            # Получаем список файлов БЕЗ распаковки
            file_list = zipf.namelist()
            
            # 1. Восстанавливаем track_data.json первым (маленький файл)
            if "track_data.json" in file_list:
                zipf.extract("track_data.json", import_dir)
                track_data_src = os.path.join(import_dir, "track_data.json")
                track_data_dst = os.path.join(BASE_DIR, "track_data.json")
                
                shutil.copy2(track_data_src, track_data_dst)
                imported_items.append("track_data.json")
                
                # Перезагружаем медиатеку
                media_library.load_from_file()
                logger.info("✅ track_data.json восстановлен")
            
            # 2. Восстанавливаем images по частям
            image_files = [f for f in file_list if f.startswith("images/") and not f.endswith('/')]
            if image_files:
                images_dst = os.path.join(BASE_DIR, "images")
                if os.path.exists(images_dst):
                    shutil.rmtree(images_dst)
                os.makedirs(images_dst)
                
                # Распаковываем по 20 файлов за раз
                for i in range(0, len(image_files), 20):
                    batch = image_files[i:i+20]
                    for file_in_zip in batch:
                        zipf.extract(file_in_zip, import_dir)
                    
                    # Очищаем память после каждой пачки
                    if i > 0 and i % 100 == 0:
                        import gc
                        gc.collect()
                
                # Копируем всю папку images
                images_src = os.path.join(import_dir, "images")
                if os.path.exists(images_src):
                    for item in os.listdir(images_src):
                        s = os.path.join(images_src, item)
                        d = os.path.join(images_dst, item)
                        if os.path.isdir(s):
                            shutil.copytree(s, d)
                        else:
                            shutil.copy2(s, d)
                    
                    image_count = len([f for f in os.listdir(images_dst) if os.path.isfile(os.path.join(images_dst, f))])
                    imported_items.append(f"images ({image_count} файлов)")
                    logger.info(f"✅ Папка images восстановлена ({image_count} файлов)")
            
            # 3. Восстанавливаем downloads по частям (САМОЕ ЭКОНОМНО)
            audio_files = [f for f in file_list if f.startswith("downloads/") and not f.endswith('/')]
            if audio_files:
                downloads_dst = os.path.join(BASE_DIR, "downloads")
                if os.path.exists(downloads_dst):
                    shutil.rmtree(downloads_dst)
                os.makedirs(downloads_dst)
                
                # Распаковываем по 10 файлов за раз (аудио тяжелые)
                processed = 0
                for i in range(0, len(audio_files), 10):
                    batch = audio_files[i:i+10]
                    for file_in_zip in batch:
                        try:
                            zipf.extract(file_in_zip, import_dir)
                            processed += 1
                            
                            # Логируем прогресс каждые 50 файлов
                            if processed % 50 == 0:
                                logger.info(f"🎵 Распаковано {processed}/{len(audio_files)} аудиофайлов")
                                import gc
                                gc.collect()
                                
                        except Exception as e:
                            logger.error(f"❌ Ошибка распаковки {file_in_zip}: {e}")
                            continue
                
                # Копируем аудиофайлы
                downloads_src = os.path.join(import_dir, "downloads")
                if os.path.exists(downloads_src):
                    audio_count = 0
                    for root, dirs, files in os.walk(downloads_src):
                        for file in files:
                            if file.lower().endswith(('.mp3', '.wav', '.flac', '.m4a', '.aac')):
                                src_path = os.path.join(root, file)
                                dst_path = os.path.join(downloads_dst, file)
                                shutil.copy2(src_path, dst_path)
                                audio_count += 1
                                
                                # Очистка памяти каждые 30 файлов
                                if audio_count % 30 == 0:
                                    import gc
                                    gc.collect()
                    
                    imported_items.append(f"downloads ({audio_count} файлов)")
                    logger.info(f"✅ Папка downloads восстановлена ({audio_count} файлов)")
        
        # ФИНАЛЬНАЯ ОЧИСТКА
        shutil.rmtree(import_dir)
        
        tracks_count = media_library.get_tracks_count()
        logger.info(f"✅ Импорт завершен: {len(imported_items)} компонентов, {tracks_count} треков")
        
        return {
            "success": True,
            "message": "Импорт данных завершен успешно",
            "imported_items": imported_items,
            "tracks_count": tracks_count
        }
        
    except zipfile.BadZipFile:
        logger.error("❌ Ошибка: поврежденный ZIP архив")
        return {"success": False, "error": "Файл поврежден или не является ZIP архивом"}
    except Exception as e:
        logger.error(f"❌ Ошибка импорта данных: {e}")
        # Очищаем временные файлы при ошибке
        try:
            if 'import_dir' in locals() and os.path.exists(import_dir):
                shutil.rmtree(import_dir)
        except:
            pass
        return {"success": False, "error": str(e)}

@app.get("/api/export/info")
async def get_export_info():
    """Получить точную информацию о данных для экспорта"""
    try:
        tracks_count = media_library.get_tracks_count()
        
        images_dir = os.path.join(BASE_DIR, "images")
        downloads_dir = os.path.join(BASE_DIR, "downloads")
        
        # ТОЧНЫЙ ПОДСЧЕТ
        images_count = 0
        downloads_count = 0
        total_size = 0
        
        if os.path.exists(images_dir):
            for file in os.listdir(images_dir):
                file_path = os.path.join(images_dir, file)
                if os.path.isfile(file_path) and file.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                    images_count += 1
                    total_size += os.path.getsize(file_path)
        
        if os.path.exists(downloads_dir):
            for file in os.listdir(downloads_dir):
                file_path = os.path.join(downloads_dir, file)
                if os.path.isfile(file_path) and file.lower().endswith(('.mp3', '.wav', '.flac', '.m4a', '.aac')):
                    downloads_count += 1
                    total_size += os.path.getsize(file_path)
        
        # Добавляем размер track_data.json
        track_data_path = os.path.join(BASE_DIR, "track_data.json")
        if os.path.exists(track_data_path):
            total_size += os.path.getsize(track_data_path)
        
        # Реальный размер с учетом компрессии (примерно 60% от исходного)
        estimated_size_mb = round((total_size * 0.6) / 1024 / 1024, 2)
        
        return {
            "success": True,
            "export_info": {
                "tracks_count": tracks_count,
                "images_count": images_count,
                "downloads_count": downloads_count,
                "estimated_size_mb": estimated_size_mb,
                "actual_size_mb": round(total_size / 1024 / 1024, 2),
                "components": [
                    "track_data.json (метаданные треков)",
                    "images/ (фото артистов)",
                    "downloads/ (аудиофайлы)"
                ]
            }
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка получения информации об экспорте: {e}")
        return {"success": False, "error": str(e)}
if __name__ == "__main__":
    import uvicorn
    logger.info("🎵 Music Loto Maker Server v3.0 Starting...")
    logger.info(f"🔧 Metadata processor: {type(metadata_processor).__name__}")
    logger.info("🎯 Key features: Smart segments, File management, Presentation generation, Duplicate checking")
    logger.info("🌐 Music download: Yandex Music only")
    logger.info(f"🌐 Server running on http://0.0.0.0:{PORT}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)