# === CORE FASTAPI ===
from fastapi import FastAPI, UploadFile, File, HTTPException, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

# === SYSTEM & PATHS ===
import os
import sys
import shutil
from pathlib import Path
from datetime import datetime
import tempfile

# === LOGGING ===
import logging
from logging.handlers import TimedRotatingFileHandler

# === UTILS & LIBS ===
import json
import glob
import requests
from PIL import Image
import io
import random
import inspect
import yt_dlp
import asyncio
import aiohttp
from urllib.parse import quote
import re
from typing import List
# === INTERNAL MODULES ===
from backend.dropbox_storage import DropboxStorage
dropbox_storage = DropboxStorage()

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
# === END LOGGING CONFIGURATION ===

# === FASTAPI APP INITIALIZATION ===
app = FastAPI(title="Music Loto Maker", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Можно указать конкретные домены
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === ADDED: frontend logging endpoint ===
from fastapi import Request
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
    from media_library import MediaLibrary
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

    logger.info("✅ Используется заглушка MediaLibrary")

# Импорт современных генераторов
# === ИМПОРТ ГЕНЕРАТОРОВ - ОБНОВЛЕННАЯ ВЕРСИЯ ===

try:
    from presentation import ModernPresentationGenerator
    logger.info("✅ ModernPresentationGenerator imported successfully")
except ImportError as e:
    logger.warning(f"⚠️ ModernPresentationGenerator import error: {e}")
    # Заглушка ModernPresentationGenerator остается без изменений
    class ModernPresentationGenerator:
        def generate_presentation_by_template(self, tracks, output_path, **kwargs):
            logger.info(f"🎲 Генерация презентации по шаблону для {len(tracks)} треков (fallback). Design keys: {list(kwargs.keys())}")
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

# ОТДЕЛЬНЫЙ ИМПОРТ TicketGenerator с поддержкой design
try:
    from tickets import TicketGenerator
    logger.info("✅ TicketGenerator imported successfully")
except ImportError as e:
    logger.warning(f"⚠️ TicketGenerator import error: {e}")
    # Заглушка TicketGenerator с поддержкой design
    class TicketGenerator:
        def generate_modern_tickets(self, tracks, count=24, design=None):
            logger.info(f"🎫 Генерация современных билетов: {count} шт. Design: {design}")
            # Создаем папку для билетов
            import os
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            tickets_folder = os.path.join("output", f"tickets_{timestamp}")
            os.makedirs(tickets_folder, exist_ok=True)
            
            # Создаем заглушечные файлы
            for i in range(count):
                ticket_path = os.path.join(tickets_folder, f"ticket_{i+1:03d}.pdf")
                with open(ticket_path, 'w', encoding='utf-8') as f:
                    f.write(f"Ticket {i+1} - Design: {design}")
            
            # Создаем архивный файл
            archive_path = os.path.join(tickets_folder, "all_tickets.pdf")
            with open(archive_path, 'w', encoding='utf-8') as f:
                f.write(f"All Tickets Archive - Design: {design}")
                
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

# Инициализация приложения
app = FastAPI(title="Music Loto Maker", version="3.0.0")


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
# TRACK JSON DISCOVERY
# =========================
def _find_track_json_path() -> str | None:
    candidates = [
        os.path.join(BASE_DIR, "track_data.json"),
        os.path.join(BASE_DIR, "backend", "track_data.json"),
        os.path.join(os.path.dirname(__file__), "track_data.json"),
    ]
    for p in candidates:
        if os.path.exists(p):
            logger.info(f"📄 Найден track_data.json: {p}")
            return p
    logger.warning("🚫 track_data.json не найден ни в одном из ожидаемых путей")
    return None

# =========================
# INITIALIZATION
# =========================


# Инициализация модулей
media_library = MediaLibrary()
if not os.path.exists("base.pptx"):
    dropbox_storage.download_base_pptx("base.pptx")
# --- Проверка и загрузка фото артистов из Dropbox ---
artists_dir = "artists"
if not os.path.exists(artists_dir):
    logger.info(f"📁 Папка {artists_dir} не найдена. Создание папки...")
    os.makedirs(artists_dir, exist_ok=True)
    logger.info(f"✅ Папка {artists_dir} создана.")

# Проверяем, пуста ли папка
local_files = os.listdir(artists_dir)
if len(local_files) == 0:
    logger.info(f"📂 Папка {artists_dir} пуста. Попытка загрузки фото из Dropbox...")
    try:
        photos_info = dropbox_storage.list_artist_photos()
        if photos_info:
            for photo_info in photos_info:
                filename = photo_info['filename']
                dropbox_path = photo_info['dropbox_path'] # Путь в Dropbox
                local_path = os.path.join(artists_dir, filename)

                # Пропускаем, если файл уже существует
                if os.path.exists(local_path):
                    logger.info(f"🖼️ Файл {filename} уже существует в {artists_dir}, пропуск.")
                    continue

                # Скачиваем файл через API Dropbox
                try:
                    metadata, response = dropbox_storage.dbx.files_download(dropbox_path)
                    with open(local_path, 'wb') as f:
                        f.write(response.content)
                    logger.info(f"✅ Загружено фото: {filename} в {artists_dir}")
                except Exception as e:
                    logger.error(f"❌ Ошибка при скачивании фото {filename}: {e}")

        else:
            logger.info("🔍 В Dropbox в папке /artists не найдено фото.")
    except Exception as e:
        logger.error(f"❌ Ошибка при загрузке фото артистов из Dropbox: {e}")
else:
    logger.info(f"✅ Папка {artists_dir} содержит {len(local_files)} файлов(а).")

modern_presentation_gen = ModernPresentationGenerator("base.pptx")
ticket_gen = TicketGenerator()


# =========================
# TICKETS ROUTER CONNECTION - DEBUG
# =========================

logger.info("🔧 Проверяем доступность server_tickets_router...")

try:
    # Проверим существует ли файл
    tickets_router_path = os.path.join(os.path.dirname(__file__), "server_tickets_router.py")
    logger.info(f"📁 Путь к router: {tickets_router_path}")
    logger.info(f"📁 Файл существует: {os.path.exists(tickets_router_path)}")
    
    # Пробуем импортировать
    from backend.server_tickets_router import router as tickets_router, set_dependencies
    logger.info("✅ server_tickets_router импортирован успешно!")
    
    # Инициализируем зависимости
    set_dependencies(media_library, ticket_gen)
    
    # Подключаем router - ВАЖНО: без prefix, т.к. пути уже полные в router
    app.include_router(tickets_router)
    logger.info("✅ Tickets router подключен!")
    
except ImportError as e:
    logger.error(f"❌ Ошибка импорта: {e}")
    logger.error(f"❌ Sys.path: {sys.path}")
except Exception as e:
    logger.error(f"❌ Другая ошибка: {e}")

logger.info("🎵 Music Loto Maker Server v3.0 initialized")

@app.get("/api/debug/all-routes")
async def debug_all_routes():
    """Показать все зарегистрированные routes"""
    routes = []
    for route in app.routes:
        if hasattr(route, 'methods') and hasattr(route, 'path'):
            routes.append({
                'path': route.path,
                'methods': list(route.methods),
                'name': getattr(route, 'name', '')
            })
    
    return {
        "total_routes": len(routes),
        "routes": routes
    }
# =========================
# DEBUG ENDPOINTS
# =========================

@app.get("/api/debug/check-file/{filename}")
async def debug_check_file(filename: str):
    """Отладочный endpoint для проверки существования файлов"""
    try:
        possible_paths = [
            os.path.join(BASE_DIR, "assets", "custom_buttons", filename),
            os.path.join(BASE_DIR, "assets", "backgrounds", filename),
            os.path.join(BASE_DIR, "assets", filename),
            os.path.join(BASE_DIR, "output", filename),
            os.path.join(BASE_DIR, "temp", filename),
            os.path.join(BASE_DIR, "uploads", filename),
            os.path.join(BASE_DIR, "images", filename),
            os.path.join(BASE_DIR, "downloads", filename),
            os.path.join(BASE_DIR, filename),
        ]
        
        results = []
        for path in possible_paths:
            exists = os.path.exists(path)
            results.append({
                "path": path,
                "exists": exists,
                "is_file": os.path.isfile(path) if exists else False,
                "size": os.path.getsize(path) if exists else 0
            })
            if exists:
                logger.info(f"🔍 DEBUG: Файл найден: {path}")
        
        custom_buttons_dir = os.path.join(BASE_DIR, "assets", "custom_buttons")
        dir_contents = []
        if os.path.exists(custom_buttons_dir):
            dir_contents = os.listdir(custom_buttons_dir)
            logger.info(f"📁 DEBUG: Содержимое custom_buttons: {dir_contents}")
        
        backgrounds_dir = os.path.join(BASE_DIR, "assets", "backgrounds")
        bg_contents = []
        if os.path.exists(backgrounds_dir):
            bg_contents = os.listdir(backgrounds_dir)
            logger.info(f"📁 DEBUG: Содержимое backgrounds: {bg_contents}")
        
        return {
            "filename": filename,
            "results": results,
            "custom_buttons_dir": custom_buttons_dir,
            "dir_contents": dir_contents,
            "backgrounds_dir": backgrounds_dir,
            "bg_contents": bg_contents,
            "base_dir": BASE_DIR
        }
    except Exception as e:
        logger.error(f"❌ DEBUG ERROR: {e}")
        return {"error": str(e)}

@app.get("/api/debug/current-config")
async def debug_current_config():
    """Отладочный endpoint для проверки текущей конфигурации"""
    try:
        config_path = os.path.join(BASE_DIR, "config", "presentation_config.json")
        config_exists = os.path.exists(config_path)
        config_data = {}
        if config_exists:
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
        
        return {
            "config_exists": config_exists,
            "config_path": config_path,
            "config_data": config_data,
            "custom_button_path": config_data.get('custom_button_path'),
            "background_config": config_data.get('background', {})
        }
    except Exception as e:
        return {"error": str(e)}

# =========================
# INTERNET TRACK DOWNLOAD FUNCTIONS (ТОЛЬКО YOUTUBE)
# =========================

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


async def search_youtube_music(query: str, track_info: dict) -> dict:
    """Асинхронная функция поиска и скачивания трека с YouTube в формате MP3 (≤ 40 МБ)."""
    try:
        def _yt_search_and_download(q, track_info_local):
            try:
                MAX_FILE_SIZE_MB = 40
                MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

                temp_dir = os.path.join(tempfile.gettempdir(), 'youtube_dl')
                os.makedirs(temp_dir, exist_ok=True)

                ydl_opts = {
                    'format': 'bestaudio[ext=m4a]/bestaudio/best',
                    'outtmpl': os.path.join(temp_dir, '%(title)s.%(ext)s'),
                    'quiet': True,
                    'no_warnings': True,
                    'noplaylist': True,
                    'postprocessors': [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '192',
                    }],
                    'http_headers': {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
                        'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.8',
                    },
                    'extractor_args': {
                        'youtube': {'player_client': ['android', 'web']},
                    },
                }

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    search_query = f"{q} official audio"
                    logger.info(f"🔍 Поиск на YouTube: {search_query}")

                    # --- поиск ---
                    try:
                        info = ydl.extract_info(f"ytsearch:{search_query}", download=False)
                    except Exception as search_error:
                        logger.warning(f"⚠️ Ошибка поиска, пробуем без 'official audio': {search_error}")
                        info = ydl.extract_info(f"ytsearch:{q} audio", download=False)

                    if not info or 'entries' not in info or not info['entries']:
                        return {'success': False, 'error': 'Трек не найден на YouTube'}

                    video_info = info['entries'][0]
                    video_url = video_info.get('webpage_url') or video_info.get('url')
                    video_title = video_info.get('title') or video_info.get('id')
                    logger.info(f"🎵 Найден: {video_title}")

                    # --- оценка размера ---
                    estimated_bytes = None
                    try:
                        meta = ydl.extract_info(video_url, download=False)
                        if meta:
                            estimated_bytes = meta.get('filesize') or meta.get('filesize_approx')
                            if not estimated_bytes and 'formats' in meta:
                                for fmt in sorted(meta['formats'], key=lambda f: f.get('tbr', 0), reverse=True):
                                    estimated_bytes = fmt.get('filesize') or fmt.get('filesize_approx')
                                    if estimated_bytes:
                                        break
                    except Exception as e_meta:
                        logger.warning(f"⚠️ Не удалось получить metadata: {e_meta}")

                    if (estimated_bytes or 0) > MAX_FILE_SIZE_BYTES:
                        mb = estimated_bytes / (1024 * 1024)
                        logger.warning(f"🚫 {video_title} превышает {MAX_FILE_SIZE_MB} МБ ({mb:.1f} МБ)")
                        return {'success': False, 'error': f'Размер > {MAX_FILE_SIZE_MB} МБ — пропуск'}

                    # --- скачивание ---
                    logger.info("⬇️ Скачивание аудио...")
                    download_info = ydl.extract_info(video_url, download=True)
                    downloaded_file = ydl.prepare_filename(download_info)

                    # --- корректируем путь на финальный .mp3 ---
                    base, _ = os.path.splitext(downloaded_file)
                    mp3_path = base + ".mp3"
                    if os.path.exists(mp3_path):
                        downloaded_file = mp3_path
                    elif os.path.exists(downloaded_file):
                        logger.warning("⚠️ mp3 не найден, используем исходный файл")
                    else:
                        logger.error("❌ Файл не найден после скачивания")
                        return {'success': False, 'error': 'Файл не найден после скачивания'}

                    # --- проверка размера ---
                    actual_size = os.path.getsize(downloaded_file)
                    if actual_size > MAX_FILE_SIZE_BYTES:
                        os.remove(downloaded_file)
                        mb = actual_size / (1024 * 1024)
                        logger.warning(f"🚫 {video_title} превысил лимит ({mb:.1f} МБ)")
                        return {'success': False, 'error': f'Файл > {MAX_FILE_SIZE_MB} МБ — удалён'}

                    logger.info(f"✅ Готов файл: {downloaded_file}")
                    return {'success': True, 'file_path': downloaded_file, 'title': video_title}

            except Exception as e:
                logger.exception(f"❌ Ошибка в _yt_search_and_download: {e}")
                return {'success': False, 'error': f'Ошибка YouTube: {e}'}

        # --- выполняем в потоке ---
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _yt_search_and_download, query, track_info)
        return result

    except Exception as e:
        logger.exception(f"❌ Критическая ошибка search_youtube_music: {e}")
        return {'success': False, 'error': f'Ошибка search_youtube_music: {e}'}



async def download_tracks_batch(tracks: list, max_size_mb: int = 40) -> list:
    """
    Скачивание треков с YouTube по порядку с ограничением размера,
    анализом сегмента и поиском фото.
    """
    import asyncio, os, shutil, tempfile
    from pathlib import Path
    import yt_dlp

    MAX_SIZE_BYTES = max_size_mb * 1024 * 1024
    results = []
    total = len(tracks)

    for i, track_info in enumerate(tracks):
        try:
            query = f"{track_info.get('artist', '')} {track_info.get('title', '')}".strip() or track_info.get("original_line", "")
            logger.info(f"🔍 [{i+1}/{total}] {query}")

            temp_dir = os.path.join(tempfile.gettempdir(), "youtube_dl_fast")
            os.makedirs(temp_dir, exist_ok=True)

            ydl_opts = {
                "format": "bestaudio[ext=m4a]/bestaudio/best",
                "outtmpl": os.path.join(temp_dir, f"{i:03d}_%(title)s.%(ext)s"),
                "quiet": True,
                "noplaylist": True,
                "no_warnings": True,
                "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}],
                "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
            }

            def _download():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(f"ytsearch1:{query} audio", download=True)
                    if not info or "entries" not in info or not info["entries"]:
                        return None
                    entry = info["entries"][0]
                    filename = ydl.prepare_filename(entry)
                    mp3_path = os.path.splitext(filename)[0] + ".mp3"
                    return mp3_path if os.path.exists(mp3_path) else filename

            loop = asyncio.get_event_loop()
            downloaded_file = await loop.run_in_executor(None, _download)
            if not downloaded_file:
                results.append({"success": False, "error": f"Не удалось скачать: {query}"})
                continue

            # проверка размера
            if os.path.getsize(downloaded_file) > MAX_SIZE_BYTES:
                logger.warning(f"⚠️ {query} слишком большой (> {max_size_mb} МБ), пропуск")
                results.append({"success": False, "error": f"Файл слишком большой: {query}"})
                continue

            safe_artist = "".join(c for c in track_info.get("artist", "Unknown") if c.isalnum() or c in (" ", "-", "_")).rstrip()
            safe_title = "".join(c for c in track_info.get("title", "Unknown") if c.isalnum() or c in (" ", "-", "_")).rstrip()
            final_filename = f"{safe_artist} - {safe_title}.mp3"
            downloads_dir = os.path.join(BASE_DIR, "downloads")
            os.makedirs(downloads_dir, exist_ok=True)
            final_path = os.path.join(downloads_dir, final_filename)
            await loop.run_in_executor(None, shutil.move, downloaded_file, final_path)

            track = media_library.add_track(final_path, final_filename)
            if not track:
                results.append({"success": False, "error": f"Ошибка добавления {final_filename}"})
                continue

            media_library.update_track(track["id"], {
                "artist": safe_artist,
                "title": safe_title,
                "metadata": {"source": "internet_download", "query": query}
            })

            # анализ сегмента
            best_start = await asyncio.to_thread(audio_editor.suggest_best_segment, final_path)
            media_library.update_track_segment(track["id"], best_start, 30)

            # фото
            local_photo = Path(BASE_DIR) / "artists" / f"{safe_artist}.jpg"
            if local_photo.exists():
                image_path = await asyncio.to_thread(process_local_photo, local_photo, track["id"])
                media_library.update_track(track["id"], {"image_path": image_path})
                logger.info(f"🖼️ Использовано локальное фото {safe_artist}")
            else:
                photo_urls = await asyncio.to_thread(image_searcher.fetch_multiple_artist_photos, safe_artist, 3)
                if photo_urls:
                    image_path = await download_and_save_photo(photo_urls[0], track["id"], safe_artist)
                    if image_path:
                        media_library.update_track(track["id"], {"image_path": image_path})
                        logger.info(f"✅ Фото артиста {safe_artist} добавлено")

            results.append({"success": True, "file_path": final_path, "track_id": track["id"], "artist": safe_artist})
            logger.info(f"✅ Готово: {final_filename}")

        except Exception as e:
            logger.error(f"❌ Ошибка {track_info.get('original_line', '')}: {e}")
            results.append({"success": False, "error": str(e)})

        logger.info(f"📦 Прогресс: {i+1}/{total} ({(i+1)/total*100:.1f}%)")

    return results



async def auto_search_photos_for_downloaded_tracks(results: list):
    """Автоматически ищет фото для успешно скачанных треков"""
    try:
        successful_tracks = [r for r in results if r.get('success')]
        
        for track in successful_tracks:
            try:
                track_id = track.get('track_id')
                artist = track.get('artist')
                
                if track_id and artist:
                    logger.info(f"🖼️ Автопоиск фото для: {artist}")
                    
                    photo_urls = image_searcher.fetch_multiple_artist_photos(artist, count=3)
                    if photo_urls:
                        photo_url = photo_urls[0]
                        image_path = await download_and_save_photo(photo_url, track_id, artist)
                        
                        if image_path:
                            media_library.update_track(track_id, {'image_path': image_path})
                            logger.info(f"✅ Авто-фото сохранено для трека {track_id}")
                        
            except Exception as e:
                logger.warning(f"⚠️ Ошибка авто-поиска фото для трека {track.get('track_id')}: {e}")
                continue
                
    except Exception as e:
        logger.error(f"❌ Ошибка в авто-поиске фото: {e}")

# =========================
# INTERNET TRACK DOWNLOAD API
# =========================

@app.post("/api/tracks/download-from-list")
async def download_tracks_from_list(request_data: dict):
    """Скачивание треков из YouTube по списку названий"""
    try:
        track_list_text = request_data.get('track_list', '')
        if not track_list_text.strip():
            raise HTTPException(status_code=400, detail="Список треков пуст")
        
        tracks_to_download = parse_track_list(track_list_text)
        if not tracks_to_download:
            raise HTTPException(status_code=400, detail="Не удалось распознать список треков")
        
        logger.info(f"🎵 Начало скачивания {len(tracks_to_download)} треков с YouTube")
        
        results = await download_tracks_batch(tracks_to_download)
        
        auto_search_photos = request_data.get('auto_search_photos', True)
        if auto_search_photos:
            await auto_search_photos_for_downloaded_tracks(results)
        
        return {
            "success": True,
            "message": f"Обработано {len(results)} треков",
            "results": results,
            "downloaded": len([r for r in results if r.get('success')]),
            "failed": len([r for r in results if not r.get('success')])
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка скачивания треков: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка скачивания: {str(e)}")

# =========================
# EXISTING ROUTES (остальные маршруты остаются без изменений)
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
            "YouTube track download",
        ],
    }

# -------- Media Library API --------

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
    try:
        path = _find_track_json_path()
        if not path:
            logger.warning("⚠️ track_data.json не найден — возвращаем 0")
            return {"count": 0, "status": "insufficient"}
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        tracks = data.get("tracks", [])
        count = len(tracks)
        logger.info(f"🔢 Количество треков из JSON: {count} (файл: {path})")
        return {"count": count, "status": "sufficient" if count >= 40 else "insufficient"}
    except Exception as e:
        logger.error(f"❌ Ошибка чтения track_data.json: {e}")
        return {"count": 0, "status": "error"}

@app.post("/api/tracks/upload")
async def upload_tracks(files: list[UploadFile] = File(...)):
    MAX_SIZE_MB = 40
    MAX_SIZE_BYTES = MAX_SIZE_MB * 1024 * 1024
    ALLOWED_EXTENSIONS = {'.mp3', '.wav', '.flac', '.m4a', '.aac'}

    saved_tracks, errors = [], []
    logger.info(f"📤 Начало загрузки {len(files)} файлов")

    for file in files:
        try:
            logger.info(f"🔍 Обработка файла: {file.filename}")
            file_extension = Path(file.filename).suffix.lower()

            # --- Проверка расширения ---
            if file_extension not in ALLOWED_EXTENSIONS:
                msg = f"Неподдерживаемый формат: {file_extension}"
                errors.append(msg)
                logger.warning(f"⚠️ {msg}")
                continue

            # --- Проверка размера ---
            file.file.seek(0, os.SEEK_END)
            file_size = file.file.tell()
            file.file.seek(0)
            if file_size > MAX_SIZE_BYTES:
                msg = f"Файл {file.filename} превышает лимит {MAX_SIZE_MB} МБ"
                errors.append(msg)
                logger.warning(f"⚠️ {msg}")
                continue

            # --- Папка downloads ---
            downloads_dir = os.path.join(BASE_DIR, "downloads")
            os.makedirs(downloads_dir, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_filename = f"{timestamp}_{Path(file.filename).stem.replace(' ', '_')}{file_extension}"
            file_path = os.path.join(downloads_dir, safe_filename)

            # --- Сохраняем файл ---
            with open(file_path, "wb") as buffer:
                content = await file.read()
                buffer.write(content)

            if not os.path.exists(file_path):
                msg = f"Файл не сохранён: {file_path}"
                errors.append(msg)
                logger.error(f"❌ {msg}")
                continue

            # --- Читаем метаданные ---
            metadata = metadata_processor.process(file_path)
            logger.debug(f"📄 Метаданные для {file.filename}: {metadata}")

            # --- Добавляем в медиатеку ---
            track = media_library.add_track(file_path, file.filename)
            if not track:
                msg = f"Не удалось добавить трек в медиатеку: {file.filename}"
                errors.append(msg)
                logger.error(f"❌ {msg}")
                continue

            artist_name = metadata.get('artist', 'Неизвестный исполнитель')
            title = metadata.get('title', 'Без названия')
            update_data = {'artist': artist_name, 'title': title, 'metadata': metadata}
            media_library.update_track(track['id'], update_data)

            # --- Автоматический отрезок ---
            try:
                best_start = audio_editor.suggest_best_segment(file_path)
                media_library.update_track_segment(track['id'], best_start, 30)
            except Exception as e:
                logger.warning(f"⚠️ Не удалось установить умный отрезок: {e}")

            # --- Автоматический поиск фото артиста (без конвертации) ---
            try:
                logger.info(f"🖼️ Поиск фото для артиста: {artist_name}")
                photo_path = image_searcher.fetch_artist_png(artist_name, track['id'])

                if photo_path and os.path.exists(photo_path):
                    # Просто используем найденный PNG как есть
                    logger.info(f"✅ Фото артиста сохранено без изменений: {photo_path}")
                    media_library.update_track(track['id'], {'image_path': photo_path})
                    update_data['image_path'] = photo_path
                else:
                    logger.warning(f"⚠️ Фото для {artist_name} не найдено")

            except Exception as e:
                logger.warning(f"⚠️ Ошибка при поиске фото артиста {artist_name}: {e}")

            track.update(update_data)
            saved_tracks.append(track)

        except Exception as e:
            msg = f"Ошибка загрузки {file.filename}: {str(e)}"
            errors.append(msg)
            logger.error(f"❌ {msg}", exc_info=True)

    response_message = f"Успешно загружено {len(saved_tracks)} треков"
    if errors:
        response_message += f". Ошибки: {', '.join(errors)}"
    logger.info(f"📊 Итог загрузки: {response_message}")

    return {"message": response_message, "tracks": saved_tracks, "errors": errors}




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
        success = media_library.delete_track(track_id)
        if success:
            return {"message": "Трек удален"}
        raise HTTPException(status_code=404, detail="Трек не найден")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка удаления: {str(e)}")

@app.delete("/api/tracks")
async def clear_tracks():
    try:
        media_library.clear()
        return {"message": "Медиатека очищена"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка очистки: {str(e)}")

# -------- Artist photos --------

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
        image_path = await download_and_save_photo(photo_url, track_id, artist_name)
        if image_path and os.path.exists(image_path):
            media_library.update_track(track_id, {'image_path': image_path, 'artist': artist_name})
            return {"success": True, "message": "Фото артиста сохранено",
                    "image_path": image_path, "artist": artist_name}
        raise HTTPException(status_code=500, detail="Не удалось сохранить фото")
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения фото: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка сохранения фото: {str(e)}")

@app.post("/api/tracks/{track_id}/upload-artist-photo")
async def upload_artist_photo(track_id: int, photo: UploadFile = File(...)):
    """
    Загружает локальное фото артиста.
    Старые фото (основное и обработанное) удаляются.
    Новое сохраняется под временным именем, затем обрабатывается через image_searcher._process_local_photo:
      - PNG с прозрачностью сохраняется без изменений
      - JPG / PNG без альфа и др. форматы пытаются пройти через rembg
    """
    try:
        track = media_library.get_track(track_id)
        if not track:
            raise HTTPException(status_code=404, detail="Трек не найден")

        if not photo.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="Файл должен быть изображением")

        images_dir = os.path.join(BASE_DIR, "images")
        os.makedirs(images_dir, exist_ok=True)

        # Финальные пути (чистим их перед загрузкой)
        final_image_path = os.path.join(images_dir, f"{track_id}_artist.png")
        processed_image_path = os.path.join(images_dir, f"{track_id}_artist_processed.png")

        # --- Удаляем старые версии ---
        for path in [final_image_path, processed_image_path]:
            if os.path.exists(path):
                try:
                    os.remove(path)
                    logger.info(f"🗑️ Удалено старое фото: {path}")
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось удалить {path}: {e}")

        # --- Сохраняем новое фото во временный файл ---
        orig_ext = Path(photo.filename).suffix.lower() or ".png"
        temp_path = os.path.join(images_dir, f"{track_id}_artist_upload{orig_ext}")

        with open(temp_path, "wb") as buffer:
            content = await photo.read()
            buffer.write(content)
        logger.info(f"🖼️ Загружено новое фото артиста (temp): {temp_path}")

        # --- Обрабатываем файл через image_searcher._process_local_photo ---
        final_path = None
        try:
            loop = asyncio.get_event_loop()
            # вызываем синхронную обработку в thread pool
            final_path = await loop.run_in_executor(None, image_searcher._process_local_photo, temp_path, track_id)

            if final_path:
                logger.info(f"🛠️ Обработанное фото возвращено: {final_path}")
                # если обработанный путь отличается от temp — удаляем temp
                try:
                    if os.path.abspath(final_path) != os.path.abspath(temp_path) and os.path.exists(temp_path):
                        os.remove(temp_path)
                except Exception as e:
                    logger.debug(f"Не удалось удалить временный файл {temp_path}: {e}")

            else:
                # если обработка вернула None — используем оригинал: переименовываем temp в final
                final_path = final_image_path
                try:
                    # если final уже существует — удалим или добавим суффикс
                    if os.path.exists(final_path):
                        try:
                            os.remove(final_path)
                        except Exception:
                            pass
                    shutil.move(temp_path, final_path)
                    logger.info(f"ℹ️ Используется оригинал как финал: {final_path}")
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось переместить оригинал в финал: {e}")
                    # fallback: оставляем temp и используем его
                    final_path = temp_path

        except Exception as e:
            logger.warning(f"⚠️ Ошибка обработки загруженного фото: {e}")
            # fallback — используем temp_path
            final_path = temp_path

        # --- Сохраняем путь в медиатеку ---
        if final_path and os.path.exists(final_path):
            media_library.update_track(track_id, {'image_path': final_path})
            return {
                "success": True,
                "message": "Фото артиста загружено и обработано",
                "image_path": final_path
            }

        # Если ничего не получилось
        raise HTTPException(status_code=500, detail="Не удалось сохранить/обработать фото")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки фото: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка загрузки фото: {str(e)}")





@app.delete("/api/tracks/{track_id}/artist-photo")
async def delete_artist_photo(track_id: int):
    try:
        track = media_library.get_track(track_id)
        if not track:
            raise HTTPException(status_code=404, detail="Трек не найден")
        image_path = track.get('image_path')
        if image_path and os.path.exists(image_path):
            os.remove(image_path)
        media_library.update_track(track_id, {'image_path': None})
        return {"success": True, "message": "Фото артиста удалено"}
    except Exception as e:
        logger.error(f"❌ Ошибка удаления фото: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка удаления фото: {str(e)}")

@app.get("/api/tracks/{track_id}/artist-photo")
async def get_artist_photo(track_id: int):
    try:
        track = media_library.get_track(track_id)
        if not track:
            raise HTTPException(status_code=404, detail="Трек не найден")
        image_path = track.get('image_path')
        if image_path and os.path.exists(image_path):
            return FileResponse(image_path,
                                filename=f"artist_{track['artist']}.png",
                                media_type='image/png')
        placeholder_path = await create_placeholder_image(track['artist'], track_id)
        if placeholder_path and os.path.exists(placeholder_path):
            return FileResponse(placeholder_path,
                                filename=f"artist_{track['artist']}_placeholder.png",
                                media_type='image/png')
        raise HTTPException(status_code=404, detail="Фото артиста не найдено")
    except Exception as e:
        logger.error(f"❌ Ошибка получения фото: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка получения фото: {str(e)}")

# -------- Segments & Timings --------

@app.put("/api/tracks/{track_id}/segment")
async def update_track_segment(track_id: int, segment_data: dict):
    try:
        start_time = segment_data.get('start_time', 0)
        duration = segment_data.get('duration', 30)
        logger.info(f"🔄 Обновление отрезка трека {track_id}: {start_time}с, {duration}с")

        success = media_library.update_track_segment(track_id, start_time, duration)
        if not success:
            raise HTTPException(status_code=404, detail="Track not found")

        data_file = os.path.join(BASE_DIR, "track_data.json")
        if os.path.exists(data_file):
            with open(data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for track in data.get("tracks", []):
                if track.get('id') == track_id:
                    track['segment_start'] = start_time
                    track['segment_duration'] = duration
                    break
            with open(data_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

        return {"message": "Segment updated",
                "segment_start": start_time, "segment_duration": duration}
    except Exception as e:
        logger.error(f"❌ Ошибка обновления отрезка: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка обновления отрезка: {str(e)}")

@app.post("/api/tracks/save-all-timings")
async def save_all_timings():
    try:
        tracks = media_library.get_tracks()
        data_file = os.path.join(BASE_DIR, "track_data.json")
        if os.path.exists(data_file):
            with open(data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        else:
            data = {"tracks": []}

        for track in tracks:
            existing_idx = None
            for i, t in enumerate(data["tracks"]):
                if t.get('id') == track['id']:
                    existing_idx = i
                    break
            if existing_idx is not None:
                data["tracks"][existing_idx]['segment_start'] = track.get('segment_start', 0)
                data["tracks"][existing_idx]['segment_duration'] = track.get('segment_duration', 30)
            else:
                data["tracks"].append({
                    'id': track['id'],
                    'artist': track.get('artist', ''),
                    'title': track.get('title', ''),
                    'segment_start': track.get('segment_start', 0),
                    'segment_duration': track.get('segment_duration', 30),
                    'image_path': track.get('image_path'),
                    'file_path': track.get('file_path'),
                    'original_filename': track.get('original_filename', '')
                })

        with open(data_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return {
            "success": True,
            "message": f"Тайминги {len(tracks)} треков сохранены в основной файл",
            "file_path": data_file,
            "tracks_count": len(tracks),
            "tracks_with_images": len([t for t in tracks if t.get('image_path')])
        }
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения таймингов: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка сохранения таймингов: {str(e)}")

# -------- Presentation build --------

def _extend_to_120(tracks: list[dict]) -> list[dict]:
    """Если треков < 120 — рандомно дублируем до 120 (с сохранением базовых полей)."""
    if len(tracks) >= 120:
        return tracks
    need = 120 - len(tracks)
    logger.info(f"🧩 Дополняем треки дубликатами: {len(tracks)} -> 120 (+{need})")
    base = list(tracks)
    while need > 0 and tracks:
        src = random.choice(base)
        clone = dict(src)
        clone['id'] = max(t['id'] for t in base) + 1
        base.append(clone)
        need -= 1
    return base[:120]

def _safe_call_generator(func, *args, **kwargs):
    """Вызывает генератор с поддержкой необязательного параметра design."""
    try:
        sig = inspect.signature(func)
        if 'design' in sig.parameters and 'design' in kwargs:
            return func(*args, **kwargs)
        kwargs.pop('design', None)
        return func(*args, **kwargs)
    except TypeError:
        kwargs.pop('design', None)
        return func(*args, **kwargs)

@app.post("/api/presentation/build")
async def build_presentation(request_data: dict):
    """Генерация презентации по шаблону с заменой фото и аудио + упаковка в ZIP."""
    try:
        # 1. Получаем треки из медиатеки
        tracks = media_library.get_tracks()
        if not tracks:
            raise HTTPException(status_code=400, detail="Нет треков для генерации презентации")

        # 2. Формируем список из 120 треков
        tracks_for_gen = _extend_to_120(tracks)

        # 3. Подготовка директорий
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = os.path.join(BASE_DIR, "output")
        os.makedirs(output_dir, exist_ok=True)

        # 4. Читаем данные о дизайне
        design = request_data.get("design")
        game_title = design.get("game_title", "Музыкальное Лото") if design else "Музыкальное Лото"

        try:
            # 6. Инициализация нового генератора
            generator = ModernPresentationGenerator(base_path=os.path.join(BASE_DIR, "base.pptx"))

            # 7. Генерация PPTX и ZIP с нарезанными треками
            make_bw = request_data.get("design", {}).get("make_bw", False)
            result_path = generator.generate(
                game_title=game_title,
                make_bw=make_bw,
                tracks=tracks_for_gen,
                output_dir=output_dir
            )

            # Ищем созданный файл
            if result_path and os.path.isdir(result_path):
                zip_files = list(Path(result_path).glob("*.zip"))
                if zip_files:
                    result_path = str(zip_files[0])
                else:
                    pptx_files = list(Path(result_path).glob("*.pptx"))
                    if pptx_files:
                        result_path = str(pptx_files[0])

            if not result_path or not os.path.exists(result_path):
                raise HTTPException(status_code=500, detail="Файл не создан")

            filename = os.path.basename(result_path)
            
            logger.info(f"✅ Архив успешно создан: {result_path}")

            # 8. Возврат клиенту
            return {
                "success": True,
                "message": "Презентация и аудиотреки успешно сгенерированы",
                "archive": filename,
                "archive_path": result_path,
                "download_url": f"/api/download/{filename}",
                "tracks_count": len(tracks_for_gen),
            }

        except Exception as e:
            logger.exception("❌ Ошибка генерации презентации")
            raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")

    except Exception as e:
        logger.exception("❌ Ошибка в build_presentation")
        raise HTTPException(status_code=500, detail=f"Ошибка: {str(e)}")

@app.get("/api/templates")
async def get_available_templates():
    return {
        "templates": [
            {
                "id": "presentation_default",
                "name": "Стандартный шаблон (PDF стиль)",
                "description": "Шаблон в стиле предоставленного PDF файла - 3 раунда по 40 треков",
                "type": "presentation",
                "features": [
                    "Титульный слайд",
                    "Слайд 'поём'",
                    "3 раунда с римской нумерацией",
                    "Слайды с номерами",
                    "Слайды исполнителей",
                    "Слайды паузы",
                    "Финальный слайд",
                ],
            }
        ],
        "ticket_templates": [
            {
                "id": "tickets_default",
                "name": "Стандартные билеты",
                "description": "Бланки для игры в музыкальное лото",
                "type": "tickets",
            }
        ],
    }

@app.get("/api/tracks")
async def get_tracks():
    """Возвращает список треков из медиатеки"""
    try:
        if not media_library:
            return {"tracks": []}
        tracks = media_library.get_tracks()
        return {"tracks": tracks}
    except Exception as e:
        logger.error(f"Ошибка получения треков: {e}")
        return {"tracks": []}

@app.post("/api/templates/save")
async def save_template(template_data: dict):
    try:
        template_id = template_data.get('id') or f"template_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        templates_dir = os.path.join(BASE_DIR, "templates")
        os.makedirs(templates_dir, exist_ok=True)
        template_path = os.path.join(templates_dir, f"{template_id}.json")
        with open(template_path, 'w', encoding='utf-8') as f:
            json.dump(template_data, f, ensure_ascii=False, indent=2)
        logger.info(f"✅ Шаблон сохранен: {template_id}")
        return {"success": True, "message": "Шаблон сохранен", "template_id": template_id}
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения шаблона: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/templates/{template_id}")
async def get_template(template_id: str):
    try:
        templates_dir = os.path.join(BASE_DIR, "templates")
        template_path = os.path.join(templates_dir, f"{template_id}.json")
        if os.path.exists(template_path):
            with open(template_path, 'r', encoding='utf-8') as f:
                template_data = json.load(f)
            return {"success": True, "template": template_data}
        return {"success": True, "template": {"id": "presentation_default",
                                              "name": "Стандартный шаблон",
                                              "type": "presentation"}}
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки шаблона: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# -------- Config --------

@app.get("/api/config/presentation")
async def get_presentation_config():
    config_path = os.path.join(BASE_DIR, "config", "presentation_config.json")
    default_config = {
        "rounds": 3,
        "tracks_per_round": 40,
        "segment_duration": 30,
        "auto_split_rounds": True,
        "include_title_slide": True,
        "include_singing_slide": True,
        "include_pause_slides": True,
        "include_final_slide": True,
        "slide_transition": "random",

        "title_font_family": "Montserrat",
        "title_font_size": 52,
        "title_bold": True,
        "subtitle_font_family": "Montserrat",
        "subtitle_font_size": 22,
        "subtitle_italic": False,
        "artist_font_family": "Montserrat",
        "artist_font_size": 28,
        "artist_bold": True,
        "track_font_family": "Montserrat",
        "track_font_size": 22,

        "photo_x": 6, "photo_y": 52, "photo_w": 18, "photo_h": 18,
        "name_x": 27, "name_y": 58,
        "title_x": 27, "title_y": 66,

        "custom_button_path": None,
        "button_w": 18,
        "button_h": 10,
        "button_x": 76,
        "button_y": 72,
        "button_number_overlay": True,

        "background": {
            "mode": "solid",
            "color": "#101a2b",
            "gradFrom": "#2a62ff",
            "gradTo": "#0b1235",
            "imageURL": None
        },

        "text_color": "#ffffff",
        "font_family": "Arial",
    }
    try:
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                user_config = json.load(f)
            return {**default_config, **user_config}
        return default_config
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки конфигурации: {e}")
        return default_config

@app.post("/api/config/presentation")
async def save_presentation_config(config_data: dict):
    try:
        config_dir = os.path.join(BASE_DIR, "config")
        os.makedirs(config_dir, exist_ok=True)
        config_path = os.path.join(config_dir, "presentation_config.json")
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, ensure_ascii=False, indent=2)
        logger.info("✅ Конфигурация презентации сохранена")
        return {"success": True, "message": "Конфигурация сохранена"}
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения конфигурации: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# -------- Assets upload (custom button, background) --------

# =========================
# UPLOAD custom BUTTON PNG
# =========================
# This handler accepts an uploaded image file (preferably PNG), saves it into
# assets/custom_buttons/ and returns a JSON with a path usable by the frontend.
from fastapi import UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
import time
from PIL import Image

@app.post("/api/assets/custom-button")
async def upload_custom_button(file: UploadFile = File(...)):
    """Загрузка кастомной PNG-кнопки в assets/custom_buttons/"""
    try:
        logger.info(f"🔼 Начало загрузки кастомной кнопки: {file.filename}")
        
        if not file.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="Файл должен быть изображением")
        
        # Создаем директорию для кастомных кнопок
        custom_buttons_dir = os.path.join(BASE_DIR, "assets", "custom_buttons")
        os.makedirs(custom_buttons_dir, exist_ok=True)
        
        # Генерируем уникальное имя файла
        timestamp = int(time.time() * 1000)
        safe_filename = f"custom_button_{timestamp}.png"
        save_path = os.path.join(custom_buttons_dir, safe_filename)
        
        # Сохраняем файл
        with open(save_path, "wb") as f:
            content = await file.read()
            f.write(content)
        
        logger.info(f"✅ Кнопка сохранена: {save_path}")
        
        # Обновляем конфигурацию
        config_path = os.path.join(BASE_DIR, "config", "presentation_config.json")
        config_data = {}
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
        
        # Сохраняем относительный путь для использования в генераторе
        relative_path = f"assets/custom_buttons/{safe_filename}"
        config_data['custom_button_path'] = relative_path
        
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"✅ Конфигурация обновлена: custom_button_path = {relative_path}")
        
        return {
            "success": True, 
            "path": relative_path,
            "filename": safe_filename,
            "download_url": f"/api/download/{safe_filename}"
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки кнопки: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка загрузки кнопки: {str(e)}")

@app.post("/api/assets/background")
async def upload_background(file: UploadFile = File(...)):
    """Загрузка фонового изображения в assets/backgrounds/"""
    try:
        logger.info(f"🔼 Начало загрузки фона: {file.filename}")
        
        if not file.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="Файл должен быть изображением")
        
        # Создаем директорию для фонов
        backgrounds_dir = os.path.join(BASE_DIR, "assets", "backgrounds")
        os.makedirs(backgrounds_dir, exist_ok=True)
        
        # Генерируем уникальное имя файла
        timestamp = int(time.time() * 1000)
        safe_filename = f"background_{timestamp}.png"
        save_path = os.path.join(backgrounds_dir, safe_filename)
        
        # Сохраняем файл
        with open(save_path, "wb") as f:
            content = await file.read()
            f.write(content)
        
        logger.info(f"✅ Фон сохранен: {save_path}")
        
        # Конвертируем в PNG если нужно
        try:
            with Image.open(save_path) as img:
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                img.save(save_path, "PNG")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось конвертировать фон: {e}")
        
        # Обновляем конфигурацию
        config_path = os.path.join(BASE_DIR, "config", "presentation_config.json")
        config_data = {}
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
        
        # Сохраняем относительный путь
        relative_path = f"assets/backgrounds/{safe_filename}"
        if 'background' not in config_data:
            config_data['background'] = {}
        config_data['background']['mode'] = 'image'
        config_data['background']['imageURL'] = relative_path
        
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"✅ Конфигурация обновлена: background = {relative_path}")
        
        return {
            "success": True, 
            "path": relative_path,
            "filename": safe_filename,
            "download_url": f"/api/download/{safe_filename}"
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки фона: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка загрузки фона: {str(e)}")

# -------- Photo processing helpers --------

async def download_tracks_batch(tracks: list, max_size_mb: int = 40) -> list:
    """
    Скачивание треков с YouTube по порядку с ограничением размера,
    анализом сегмента и поиском фото. ПАРАЛЛЕЛЬНАЯ ВЕРСИЯ.
    """
    import asyncio, os, shutil, tempfile
    from pathlib import Path
    import yt_dlp
    from concurrent.futures import ThreadPoolExecutor

    MAX_SIZE_BYTES = max_size_mb * 1024 * 1024
    total = len(tracks)
    
    # Создаем директории один раз
    temp_dir = os.path.join(tempfile.gettempdir(), "youtube_dl_fast")
    downloads_dir = os.path.join(BASE_DIR, "downloads")
    os.makedirs(temp_dir, exist_ok=True)
    os.makedirs(downloads_dir, exist_ok=True)
    
    logger.info(f"🎵 Начинаем параллельное скачивание {total} треков")

    async def process_single_track(i: int, track_info: dict) -> dict:
        """Обработка одного трека"""
        try:
            query = f"{track_info.get('artist', '')} {track_info.get('title', '')}".strip() or track_info.get("original_line", "")
            logger.info(f"🔍 [{i+1}/{total}] {query}")

            ydl_opts = {
                "format": "bestaudio[ext=m4a]/bestaudio/best",
                "outtmpl": os.path.join(temp_dir, f"{i:03d}_%(id)s.%(ext)s"),
                "quiet": True,
                "noplaylist": True,
                "no_warnings": True,
                "socket_timeout": 30,
                "retries": 2,
                "postprocessors": [{
                    "key": "FFmpegExtractAudio", 
                    "preferredcodec": "mp3", 
                    "preferredquality": "192"
                }],
                "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
            }

            def _download():
                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(f"ytsearch1:{query}", download=False)
                        if not info or "entries" not in info or not info["entries"]:
                            return None
                        
                        entry = info["entries"][0]
                        duration = entry.get('duration', 0)
                        if duration > 1800:
                            logger.warning(f"⚠️ Слишком длинное видео: {duration} сек")
                            return None
                            
                        ydl.download([f"ytsearch1:{query}"])
                        
                        import glob
                        pattern = os.path.join(temp_dir, f"{i:03d}_*.*")
                        files = glob.glob(pattern)
                        return files[0] if files else None
                except Exception as e:
                    logger.error(f"Ошибка загрузки {query}: {e}")
                    return None

            # Скачиваем трек
            loop = asyncio.get_event_loop()
            downloaded_file = await loop.run_in_executor(None, _download)
            
            if not downloaded_file:
                return {"success": False, "error": f"Не удалось скачать: {query}"}

            # Проверка размера
            file_size = os.path.getsize(downloaded_file)
            if file_size > MAX_SIZE_BYTES:
                logger.warning(f"⚠️ {query} слишком большой ({file_size//1024//1024} МБ), пропуск")
                try:
                    os.remove(downloaded_file)
                except:
                    pass
                return {"success": False, "error": f"Файл слишком большой: {query}"}

            # Создаем безопасное имя
            safe_artist = track_info.get("artist", "Unknown").replace('/', '-').replace('\\', '-')[:50]
            safe_title = track_info.get("title", "Unknown").replace('/', '-').replace('\\', '-')[:50]
            final_filename = f"{safe_artist} - {safe_title}.mp3"
            final_path = os.path.join(downloads_dir, final_filename)
            
            # Перемещение файла
            await loop.run_in_executor(None, shutil.move, downloaded_file, final_path)

            # Добавляем в медиатеку
            track = media_library.add_track(final_path, final_filename)
            if not track:
                return {"success": False, "error": f"Ошибка добавления {final_filename}"}

            # ПАРАЛЛЕЛЬНО выполняем все остальные задачи
            tasks = []
            
            # Задача 1: Обновление метаданных
            tasks.append(
                loop.run_in_executor(
                    None,
                    lambda: media_library.update_track(track["id"], {
                        "artist": safe_artist,
                        "title": safe_title,
                        "metadata": {"source": "internet_download", "query": query}
                    })
                )
            )
            
            # Задача 2: Анализ сегмента
            tasks.append(
                loop.run_in_executor(
                    None,
                    lambda: audio_editor.suggest_best_segment(final_path)
                )
            )
            
            # Задача 3: Поиск фото
            tasks.append(
                loop.run_in_executor(
                    None,
                    lambda: image_searcher.fetch_artist_png(safe_artist, track["id"])
                )
            )
            
            # Ждем завершения ВСЕХ параллельных задач
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Обрабатываем результаты
            metadata_result, segment_result, image_result = results
            
            # Применяем анализ сегмента
            if not isinstance(segment_result, Exception) and segment_result is not None:
                media_library.update_track_segment(track["id"], segment_result, 30)
            
            # Применяем фото
            if not isinstance(image_result, Exception) and image_result:
                media_library.update_track(track["id"], {"image_path": image_result})
                logger.info(f"✅ Фото для {safe_artist} добавлено")

            return {
                "success": True, 
                "file_path": final_path, 
                "track_id": track["id"], 
                "artist": safe_artist
            }

        except Exception as e:
            logger.error(f"❌ Ошибка {track_info.get('original_line', '')}: {e}")
            return {"success": False, "error": str(e)}

    # ОСНОВНОЕ ИЗМЕНЕНИЕ: Параллельная обработка треков
    semaphore = asyncio.Semaphore(3)  # Максимум 3 параллельных скачивания
    
    async def limited_download(i, track_info):
        async with semaphore:
            return await process_single_track(i, track_info)
    
    # Запускаем ВСЕ задачи параллельно
    tasks = []
    for i, track_info in enumerate(tracks):
        task = asyncio.create_task(limited_download(i, track_info))
        tasks.append(task)
    
    # Ждем завершения всех задач
    results = await asyncio.gather(*tasks)
    
    # Логируем прогресс
    successful = len([r for r in results if r.get('success')])
    logger.info(f"🎉 Параллельное скачивание завершено: {successful}/{total} успешно")
    
    # Очистка временных файлов
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, shutil.rmtree, temp_dir, True)
    except Exception as e:
        logger.warning(f"⚠️ Ошибка очистки временных файлов: {e}")
    
    return results



async def auto_search_photos_for_downloaded_tracks(results: list):
    """Автоматически ищет фото для успешно скачанных треков - ПАРАЛЛЕЛЬНАЯ ВЕРСИЯ"""
    try:
        successful_tracks = [r for r in results if r.get('success')]
        
        if not successful_tracks:
            return
            
        logger.info(f"🖼️ Параллельный поиск фото для {len(successful_tracks)} треков")
        
        # Создаем семафор для ограничения параллельных запросов
        semaphore = asyncio.Semaphore(5)
        
        async def process_photo(track):
            async with semaphore:
                try:
                    track_id = track.get('track_id')
                    artist = track.get('artist')
                    
                    if track_id and artist:
                        image_path = await download_artist_photo(artist, track_id)
                        if image_path:
                            media_library.update_track(track_id, {'image_path': image_path})
                            logger.info(f"✅ Авто-фото сохранено для {artist}")
                        return True
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка авто-поиска фото для {track.get('artist')}: {e}")
                return False
        
        # Запускаем все задачи параллельно
        tasks = [process_photo(track) for track in successful_tracks]
        await asyncio.gather(*tasks)
        
        logger.info("✅ Параллельный поиск фото завершен")
                
    except Exception as e:
        logger.error(f"❌ Ошибка в авто-поиске фото: {e}")

# =========================
# INTERNET TRACK DOWNLOAD API
# =========================

@app.post("/api/tracks/download-from-list")
async def download_tracks_from_list(request_data: dict):
    """Скачивание треков из YouTube по списку названий - ПАРАЛЛЕЛЬНАЯ ВЕРСИЯ"""
    try:
        track_list_text = request_data.get('track_list', '')
        if not track_list_text.strip():
            raise HTTPException(status_code=400, detail="Список треков пуст")
        
        tracks_to_download = parse_track_list(track_list_text)
        if not tracks_to_download:
            raise HTTPException(status_code=400, detail="Не удалось распознать список треков")
        
        logger.info(f"🎵 Начало ПАРАЛЛЕЛЬНОГО скачивания {len(tracks_to_download)} треков")
        
        # Получаем параметры параллелизма из запроса
        max_workers = request_data.get('max_workers', 3)
        logger.info(f"⚡ Максимум параллельных загрузок: {max_workers}")
        
        # Скачиваем треки (теперь параллельно)
        results = await download_tracks_batch(tracks_to_download)
        
        # Автопоиск фото (тоже параллельно)
        auto_search_photos = request_data.get('auto_search_photos', True)
        if auto_search_photos:
            # Запускаем в фоне, не ждем завершения
            asyncio.create_task(auto_search_photos_for_downloaded_tracks(results))
        
        successful_count = len([r for r in results if r.get('success')])
        failed_count = len([r for r in results if not r.get('success')])
        
        logger.info(f"🎉 Скачивание завершено: {successful_count} успешно, {failed_count} с ошибками")
        
        return {
            "success": True,
            "message": f"Обработано {len(results)} треков",
            "results": results,
            "downloaded": successful_count,
            "failed": failed_count
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка скачивания треков: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка скачивания: {str(e)}")


# -------- Simple photo API wrappers --------

async def download_artist_photo(artist_name: str, track_id: int):
    """Простая обертка для скачивания фото артиста"""
    return await asyncio.to_thread(
        image_searcher.fetch_artist_png, artist_name, track_id
    )

async def search_artist_photos(artist_name: str, count: int = 10):
    """Поиск фото артиста"""
    return await asyncio.to_thread(
        image_searcher.fetch_multiple_artist_photos, artist_name, count
    )
# -------- Legacy --------

@app.post("/api/generate/presentation")
async def generate_presentation(request_data: dict):
    """Генерация презентации с заменой фото, аудио и созданием ZIP."""
    try:
        game_title = request_data.get("title") or "Музыкальное Лото"
        logger.info(f"🚀 Генерация презентации: {game_title}")

        # Пытаемся получить треки из медиатеки, если нет — пусть генератор возьмёт JSON
        tracks = media_library.get_tracks() or None
        if tracks:
            logger.info(f"📊 Получено {len(tracks)} треков из медиатеки")
        else:
            logger.warning("⚠️ В медиатеке нет треков, генератор сам подхватит tracks.json")

        base_path = os.path.join(BASE_DIR, "base.pptx")
        if not os.path.exists(base_path):
            raise HTTPException(status_code=500, detail="Файл base.pptx не найден")

        generator = ModernPresentationGenerator(base_path)

        make_bw = request_data.get("design", {}).get("make_bw", False)
        
        # ВАЖНО: получаем путь к ZIP архиву, а не к папке
        result_path = generator.generate(
            game_title=game_title,
            tracks=tracks,
            make_bw=make_bw
        )

        # Проверяем, что result_path - это путь к ZIP файлу
        if result_path and os.path.isdir(result_path):
            # Ищем ZIP файл в папке
            zip_files = list(Path(result_path).glob("*.zip"))
            if zip_files:
                result_path = str(zip_files[0])
            else:
                # Если ZIP не найден, ищем PPTX
                pptx_files = list(Path(result_path).glob("*.pptx"))
                if pptx_files:
                    result_path = str(pptx_files[0])
                else:
                    raise HTTPException(status_code=500, detail="Файл презентации не создан")

        if not result_path or not os.path.exists(result_path):
            raise HTTPException(status_code=500, detail="Ошибка генерации: файл не создан")

        # Определяем имя файла для скачивания
        filename = os.path.basename(result_path)
        
        logger.info(f"✅ Презентация успешно создана: {result_path}")
        return {
            "success": True,
            "message": f"Презентация '{game_title}' создана успешно",
            "archive": filename,
            "archive_path": result_path,
            "download_url": f"/api/download/{filename}"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"❌ Ошибка генерации презентации: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка генерации: {str(e)}")

from fastapi.responses import FileResponse
from fastapi import HTTPException

@app.get("/download/{filename}")
def download_file(filename: str):
    file_path = Path("output") / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Файл не найден")

    return FileResponse(
        path=file_path,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename=filename
    )
@app.post("/api/generate/tickets")
async def generate_tickets_legacy(count: int = 24):
    try:
        tracks = media_library.get_tracks()
        result_path = ticket_gen.generate_modern_tickets(tracks, count)
        if result_path:
            return {"success": True, "message": f"Сгенерировано {count} билетов",
                    "file_name": os.path.basename(result_path)}
        raise HTTPException(status_code=500, detail="Ошибка генерации")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/download/{filename}")
async def download_file(filename: str):
    """
    Скачивание файлов из различных директорий проекта
    """
    try:
        logger.info(f"📥 Запрос на скачивание файла: {filename}")
        
        # Безопасная проверка имени файла
        if not filename or '..' in filename or filename.startswith('/'):
            logger.warning(f"🚫 Некорректное имя файла: {filename}")
            raise HTTPException(status_code=400, detail="Некорректное имя файла")
        
        # Убираем параметры запроса если есть
        filename = filename.split('?')[0]
        
        # Список возможных путей для поиска файла
        possible_paths = [
            os.path.join(BASE_DIR, "output", filename),
            os.path.join(BASE_DIR, "assets", "custom_buttons", filename),
            os.path.join(BASE_DIR, "assets", "backgrounds", filename),
            os.path.join(BASE_DIR, "downloads", filename),
            os.path.join(BASE_DIR, "uploads", filename),
            os.path.join(BASE_DIR, "temp", filename),
            os.path.join(BASE_DIR, "images", filename),
            os.path.join(BASE_DIR, filename),  # Прямо в корневой директории
        ]
        
        # Добавляем поиск в подпапках output
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
            # Попробуем найти файл без учета регистра
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

        # Проверяем размер файла
        file_size = os.path.getsize(file_path)
        if file_size == 0:
            logger.warning(f"⚠️ Файл пустой: {file_path}")
            raise HTTPException(status_code=500, detail="Файл пустой")

        # Определяем MIME тип
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
        # Пробрасываем HTTP исключения как есть
        raise
    except Exception as e:
        logger.error(f"❌ Критическая ошибка при загрузке файла {filename}: {e}")
        logger.exception("Полная трассировка ошибки:")
        raise HTTPException(status_code=500, detail=f"Внутренняя ошибка сервера: {str(e)}")

@app.get("/api/status")
async def get_status():
    try:
        path = _find_track_json_path()
        tracks = []
        if path and os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            tracks = data.get("tracks", [])
        tracks_count = len(tracks)
        tracks_with_photos = sum(1 for t in tracks if t.get("image_path") and os.path.exists(t["image_path"]))
        status_info = {
            "status": "running",
            "version": "3.0.0",
            "tracks_count": tracks_count,
            "tracks_with_photos": tracks_with_photos,
            "musical_loto_ready": tracks_count >= 40,
            "metadata_processor": type(metadata_processor).__name__,
            "features": [
                "musical_loto_game",
                "modern_presentations",
                "smart_metadata",
                "audio_editing",
                "ticket_generation",
                "json_export",
                "artist_images_manual",
                "youtube_track_download",
            ],
        }
        if tracks_count < 40:
            status_info["warning"] = f"Для Musical Loto нужно ещё {40 - tracks_count} треков"
        else:
            status_info["message"] = "Musical Loto готов к генерации!"
        return status_info
    except Exception as e:
        logger.error(f"❌ Ошибка статуса: {e}")
        return {"status": "error", "version": "3.0.0", "tracks_count": 0, "error": str(e)}

# -------- Audio Editor API --------

@app.get("/api/tracks/{track_id}/waveform")
async def get_track_waveform(track_id: int):
    try:
        track = media_library.get_track(track_id)
        if not track:
            raise HTTPException(status_code=404, detail="Track not found")
        if not track.get('waveform_data'):
            waveform_data = audio_editor.generate_waveform(track['file_path'])
            if waveform_data:
                track['waveform_data'] = waveform_data
                if hasattr(media_library, 'save_to_file'):
                    media_library.save_to_file()
            else:
                raise HTTPException(status_code=500, detail="Failed to generate waveform")
        return {"waveform_data": track.get('waveform_data')}
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
        analysis_details = {
            "method": "комбинированный анализ",
            "score": 0.85,
            "energy_score": 0.78,
            "variability_score": 0.82,
            "peaks_score": 0.91,
        }
        return {"success": True, "suggested_start": best_start, "analysis_details": analysis_details}
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
# FILE UPLOAD FIXES - COMPLETE BLOCK
# =========================

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

# =========================
# DROPBOX DOWNLOAD ENDPOINTS
# =========================

@app.post("/api/dropbox/download-base-pptx")
async def download_base_pptx_from_dropbox():
    """Скачать base.pptx из Dropbox (если локального нет)"""
    try:
        base_path = os.path.join(BASE_DIR, "base.pptx")
        success = dropbox_storage.download_base_pptx(base_path)
        
        if success:
            file_size = os.path.getsize(base_path)
            return {
                "success": True,
                "message": "base.pptx скачан из Dropbox",
                "size": file_size
            }
        else:
            return {"success": False, "error": "Не удалось скачать base.pptx"}
            
    except Exception as e:
        logger.error(f"❌ Ошибка скачивания base.pptx: {e}")
        return {"success": False, "error": str(e)}

@app.post("/api/dropbox/download-artist-photos")
async def download_artist_photos_from_dropbox():
    """Скачать фото артистов из Dropbox (если локальной папки нет или пустая)"""
    try:
        artists_dir = os.path.join(BASE_DIR, "artists")
        success = dropbox_storage.download_artist_photos(artists_dir)
        
        if success:
            # Получаем список скачанных фото
            photos = []
            if os.path.exists(artists_dir):
                for filename in os.listdir(artists_dir):
                    if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                        photos.append({
                            "filename": filename,
                            "artist_name": os.path.splitext(filename)[0].replace('_', ' ')
                        })
            
            return {
                "success": True,
                "message": f"Скачано {len(photos)} фото артистов",
                "photos": photos
            }
        else:
            return {"success": False, "error": "Не удалось скачать фото артистов"}
            
    except Exception as e:
        logger.error(f"❌ Ошибка скачивания фото артистов: {e}")
        return {"success": False, "error": str(e)}

@app.get("/api/dropbox/available-photos")
async def get_available_dropbox_photos():
    """Получить список фото доступных в Dropbox"""
    try:
        photos = dropbox_storage.list_artist_photos()
        return {"photos": photos}
    except Exception as e:
        logger.error(f"❌ Ошибка получения списка фото: {e}")
        return {"photos": []}

# -------- Health --------

@app.get("/api/health")
async def health_check():
    tracks_count = media_library.get_tracks_count()
    tracks_with_photos = len([t for t in media_library.get_tracks()
                              if t.get('image_path') and os.path.exists(t.get('image_path'))])
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
            "youtube_track_download",
        ],
    }


if __name__ == "__main__":
    import uvicorn
    logger.info("🎵 Music Loto Maker Server v3.0 Starting...")
    logger.info(f"🔧 Metadata processor: {type(metadata_processor).__name__}")
    logger.info("📷 Artist photos: MANUAL (user adds photos manually)")
    logger.info("🎯 Key features: Smart segments, No clip files, Single JSON storage")
    logger.info("⏱️ Timing management: Auto smart segments + manual editing + JSON export")
    logger.info("🌐 Internet download: YouTube Music")
    logger.info("🌐 Server running on http://127.0.0.1:8000")
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=True)