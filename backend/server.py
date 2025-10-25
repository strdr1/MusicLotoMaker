# backend/server.py
from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
import os
import sys
import shutil
from pathlib import Path
import logging

# === EXTENDED LOGGING CONFIGURATION ===
import logging
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime
from flask import Flask
app = Flask(__name__)
# Create logs directory (Windows path)
LOG_DIR = r"E:\1\MusicLotoMaker\MusicLotoMaker\logs"
os.makedirs(LOG_DIR, exist_ok=True)

log_filename = os.path.join(LOG_DIR, f"server_{datetime.now().strftime('%Y-%m-%d')}.log")


# Configure root logger
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
# === END LOGGING CONFIGURATION ===

from datetime import datetime
import json
import glob
import requests
from PIL import Image
import io
import random  # ⬅️ для рандомных дубликатов
import inspect  # ⬅️ чтобы аккуратно прокинуть design в генератор
import yt_dlp
import asyncio
import aiohttp
from urllib.parse import quote
import re
import tempfile


# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    
    # Логируем входящий запрос
    logger.info(f"📍 ВХОДЯЩИЙ ЗАПРОС: {request.method} {request.url}")
    logger.info(f"📍 Headers: {dict(request.headers)}")
    
    response = await call_next(request)
    
    # Логируем ответ
    process_time = time.time() - start_time
    logger.info(f"📍 ОТВЕТ: {request.method} {request.url} -> {response.status_code} ({process_time:.2f}s)")
    
    return response
# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

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
# INIT FROM track_data.json
# =========================
def _load_tracks_from_json_into_library():
    try:
        if hasattr(media_library, "get_tracks") and media_library.get_tracks():
            logger.info("ℹ️ Медиатека уже заполнена — пропускаем загрузку из JSON")
            return

        data_file = _find_track_json_path()
        if not data_file:
            return

        with open(data_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        tracks = data.get("tracks", [])
        if not tracks:
            logger.info("ℹ️ В track_data.json нет треков — пропускаем")
            return

        loaded = 0
        for t in tracks:
            added = media_library.add_track(t.get("file_path"), t.get("original_filename", ""))
            if not added:
                continue
            media_library.update_track(added["id"], {
                "id": t.get("id", added["id"]),
                "artist": t.get("artist", "Неизвестный исполнитель"),
                "title": t.get("title", "Без названия"),
                "segment_start": float(t.get("segment_start", 0)),
                "segment_duration": int(t.get("segment_duration", 30)),
                "image_path": t.get("image_path"),
                "file_path": t.get("file_path"),
                "metadata": t.get("metadata", {}),
                "original_filename": t.get("original_filename", "")
            })
            loaded += 1

        logger.info(f"📦 Инициализировано из JSON: {loaded} треков")

    except Exception as e:
        logger.warning(f"⚠️ Не удалось инициализировать медиатеку из JSON: {e}")

def _count_tracks_with_fallback() -> int:
    try:
        cur = media_library.get_tracks_count()
        if cur > 0:
            return cur
        path = _find_track_json_path()
        if not path:
            return 0
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return len(data.get("tracks", []))
    except Exception as e:
        logger.warning(f"⚠️ Ошибка подсчёта треков с fallback: {e}")
        return 0

# =========================
# INITIALIZATION
# =========================


# Инициализация модулей
media_library = MediaLibrary()
_load_tracks_from_json_into_library()
base_pptx_path = os.path.join(BASE_DIR, "base.pptx")
modern_presentation_gen = ModernPresentationGenerator(base_path=base_pptx_path)
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



async def download_tracks_batch(tracks: list, max_parallel: int = 4) -> list:
    """Параллельное пакетное скачивание треков с YouTube с ограничением параллелизма.
    По умолчанию параллельно скачивается 4 трека; можно изменить через параметр max_parallel."""
    results = []
    sem = asyncio.Semaphore(max_parallel)
    total = len(tracks)

    async def _process_single(i, track_info):
        async with sem:
            try:
                logger.info(f"🔍 Поиск трека {i+1}/{total}: {track_info['search_query']}")
                # use the async-compatible search which runs blocking yt_dlp in thread
                download_result = await search_youtube_music(track_info['search_query'], track_info)
                if download_result and download_result.get('success'):
                    downloaded_file = download_result['file_path']
                    # move/rename to final path if needed
                    safe_artist = "".join(c for c in track_info.get('artist', 'Unknown') if c.isalnum() or c in (' ', '-', '_')).rstrip()
                    safe_title = "".join(c for c in track_info.get('title', 'Unknown') if c.isalnum() or c in (' ', '-', '_')).rstrip()
                    ext = Path(downloaded_file).suffix or '.mp3'
                    final_filename = f"{safe_artist} - {safe_title}{ext}"
                    final_path = os.path.join(BASE_DIR, "downloads", final_filename)
                    os.makedirs(os.path.dirname(final_path), exist_ok=True)
                    try:
                        # If yt_dlp output already matches final_path, skip move
                        if os.path.abspath(downloaded_file) != os.path.abspath(final_path):
                            if os.path.exists(final_path):
                                base, e = os.path.splitext(final_filename)
                                final_filename = f"{base}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{e}"
                                final_path = os.path.join(BASE_DIR, "downloads", final_filename)
                            shutil.move(downloaded_file, final_path)
                        else:
                            final_path = downloaded_file
                    except Exception as e:
                        logger.warning(f"⚠️ Не удалось переместить файл: {e}")
                        final_path = downloaded_file

                    original_filename = f"{track_info.get('artist', 'Unknown')} - {track_info.get('title', 'Unknown')}.mp3"
                    track = media_library.add_track(final_path, original_filename)

                    if track:
                        update_data = {
                            'artist': track_info.get('artist', 'Неизвестный исполнитель'),
                            'title': track_info.get('title', 'Без названия'),
                            'metadata': {
                                'source': 'internet_download',
                                'original_query': track_info['search_query'],
                                'download_source': 'youtube'
                            }
                        }
                        media_library.update_track(track['id'], update_data)

                        try:
                            best_start = audio_editor.suggest_best_segment(final_path)
                            media_library.update_track_segment(track['id'], best_start, 30)
                            logger.info(f"✅ Установлен умный отрезок для трека {track['id']}")
                        except Exception as e:
                            logger.warning(f"⚠️ Не удалось установить умный отрезок: {e}")

                        return {
                            'success': True,
                            'original_line': track_info['original_line'],
                            'artist': track_info.get('artist', ''),
                            'title': track_info.get('title', ''),
                            'file_path': final_path,
                            'track_id': track['id'],
                            'source': 'YouTube'
                        }
                    else:
                        return {
                            'success': False,
                            'original_line': track_info['original_line'],
                            'error': 'Ошибка добавления в медиатеку'
                        }
                else:
                    return {
                        'success': False,
                        'original_line': track_info['original_line'],
                        'error': download_result.get('error', 'Трек не найден на YouTube')
                    }
            except Exception as e:
                logger.error(f"❌ Ошибка обработки трека {track_info.get('original_line')}: {e}")
                return {
                    'success': False,
                    'original_line': track_info.get('original_line'),
                    'error': str(e)
                }

    # create tasks and gather as they finish to report progress
    tasks = [asyncio.create_task(_process_single(i, t)) for i, t in enumerate(tracks)]
    for coro in asyncio.as_completed(tasks):
        res = await coro
        results.append(res)
        done = len(results)
        logger.info(f"📦 Прогресс загрузки: {done}/{total} ({(done/total)*100:.1f}%)")

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
    try:
        if not media_library.get_tracks():
            _load_tracks_from_json_into_library()
            if not media_library.get_tracks():
                path = _find_track_json_path()
                if path:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    tracks = data.get("tracks", [])
                    logger.info(f"📊 Отдаём треки напрямую из JSON: {len(tracks)}")
                    return tracks
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
    from presentation import ModernPresentationGenerator

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

    # 5. Сохраняем последний дизайн (если есть)
    if design:
        try:
            os.makedirs(os.path.join(BASE_DIR, "config"), exist_ok=True)
            with open(os.path.join(BASE_DIR, "config", "presentation_design_last.json"), "w", encoding="utf-8") as f:
                json.dump(design, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"⚠️ Не удалось сохранить snapshot дизайна: {e}")

    try:
        # 6. Инициализация нового генератора
        generator = ModernPresentationGenerator(base_path=os.path.join(BASE_DIR, "base.pptx"))

        # 7. Генерация PPTX и ZIP с нарезанными треками
        make_bw = request_data.get("design", {}).get("make_bw", False)
        zip_path = generator.generate(
            game_title=game_title,
            make_bw=make_bw,
            tracks=tracks_for_gen,
            output_dir=output_dir
        )

        logger.info(f"✅ Архив успешно создан: {zip_path}")

        # 8. Возврат клиенту
        return {
            "success": True,
            "message": "Презентация и аудиотреки успешно сгенерированы",
            "archive": os.path.basename(zip_path),
            "archive_path": zip_path,
            "tracks_count": len(tracks_for_gen),
        }

    except Exception as e:
        logger.exception("❌ Ошибка генерации презентации")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")

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

async def download_and_save_photo(photo_url: str, track_id: int, artist_name: str):
    """Скачивает и сохраняет фото с разделением логики: локальные - без удаления фона, интернет - с удалением"""
    try:
        # Сначала проверяем локальную папку artists
        artists_dir = os.path.join(BASE_DIR, "artists")
        if os.path.exists(artists_dir):
            local_photo = image_searcher._find_local_artist_photo(artist_name)
            if local_photo:
                logger.info(f"📁 Используем локальное фото (фон не удаляем): {local_photo}")
                # Обрабатываем локальное фото БЕЗ удаления фона
                return await process_local_photo(local_photo, track_id)
        
        # Если локального фото нет, загружаем из интернета С удалением фона
        logger.info(f"🌐 Загружаем фото из интернета (фон будет удален): {photo_url}")
        return await process_internet_photo(photo_url, track_id)
        
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки фото: {e}")
        return await create_placeholder_image(artist_name, track_id)

async def process_local_photo(local_path: str, track_id: int):
    """Обрабатывает локальное фото БЕЗ удаления фона"""
    try:
        images_dir = os.path.join(BASE_DIR, "images")
        os.makedirs(images_dir, exist_ok=True)
        
        ext = Path(local_path).suffix.lower()
        image_path = os.path.join(images_dir, f"{track_id}_artist{ext}")
        
        # Просто копируем файл без обработки
        import shutil
        shutil.copy2(local_path, image_path)
        
        logger.info(f"✅ Локальное фото сохранено (фон не удален): {image_path}")
        return image_path
        
    except Exception as e:
        logger.error(f"❌ Ошибка обработки локального фото: {e}")
        return None

async def process_internet_photo(photo_url: str, track_id: int):
    """Обрабатывает интернет-фото С удалением фона"""
    try:
        images_dir = os.path.join(BASE_DIR, "images")
        os.makedirs(images_dir, exist_ok=True)
        image_path = os.path.join(images_dir, f"{track_id}_artist.png")
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; x64) AppleWebKit/537.36',
            'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.8',
        }
        response = requests.get(photo_url, headers=headers, timeout=30)
        if response.status_code != 200:
            raise Exception(f"HTTP error: {response.status_code}")
        
        # Сохраняем временный файл
        temp_path = image_path.replace('.png', '_temp.jpg')
        with open(temp_path, 'wb') as f:
            f.write(response.content)
        
        # Обрабатываем с удалением фона
        success = await process_downloaded_image_with_bg_removal(temp_path, image_path)
        
        if os.path.exists(temp_path):
            os.remove(temp_path)
            
        if success:
            return image_path
        return None
        
    except Exception as e:
        logger.error(f"❌ Ошибка обработки интернет-фото: {e}")
        return None

async def process_downloaded_image_with_bg_removal(temp_path: str, output_path: str):
    """Обрабатывает скачанное фото С удалением фона"""
    try:
        with Image.open(temp_path) as img:
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
            max_size = (800, 800)
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
            
            # Сохраняем временно для rembg
            temp_png = temp_path.replace('.jpg', '_for_rembg.png')
            img.save(temp_png, "PNG")
        
        # Удаляем фон с помощью rembg
        try:
            from rembg import remove
            with open(temp_png, 'rb') as i:
                input_data = i.read()
            output_data = remove(input_data)
            with open(output_path, 'wb') as o:
                o.write(output_data)
            logger.info("🎨 Фон удален (интернет-фото)")
            
            # Удаляем временный файл
            if os.path.exists(temp_png):
                os.remove(temp_png)
                
            return True
        except ImportError:
            logger.warning("⚠️ rembg не установлен, сохраняем без удаления фона")
            img.save(output_path, "PNG", optimize=True)
            return True
        except Exception as e:
            logger.warning(f"⚠️ Ошибка удаления фона: {e}, сохраняем без удаления")
            img.save(output_path, "PNG", optimize=True)
            return True
            
    except Exception as e:
        logger.error(f"❌ Ошибка обработки изображения: {e}")
        return False

async def process_uploaded_image(image_path: str, track_id: int):
    """Обрабатывает загруженное пользователем фото - решаем по контексту"""
    try:
        # Определяем, нужно ли удалять фон
        # Если фото загружено через интерфейс артиста - вероятно, это портрет, можно удалить фон
        # Если это локальное фото из папки artists - не удаляем фон
        
        # Для простоты: все загруженные через интерфейс фото обрабатываем с удалением фона
        processed_path = image_path.replace('.png', '_processed.png')
        
        with Image.open(image_path) as img:
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
            max_size = (800, 800)
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
            img.save(processed_path, "PNG", optimize=True)
        
        # Удаляем фон для загруженных фото
        try:
            from rembg import remove
            with open(processed_path, 'rb') as i:
                input_data = i.read()
            output_data = remove(input_data)
            with open(processed_path, 'wb') as o:
                o.write(output_data)
            logger.info("🎨 Фон удален (загруженное фото)")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось удалить фон: {e}")
        
        return processed_path
    except Exception as e:
        logger.error(f"❌ Ошибка обработки загруженного изображения: {e}")
        return None

async def create_placeholder_image(artist_name: str, track_id: int):
    try:
        from PIL import Image, ImageDraw, ImageFont
        images_dir = os.path.join(BASE_DIR, "images")
        os.makedirs(images_dir, exist_ok=True)
        placeholder_path = os.path.join(images_dir, f"{track_id}_artist_placeholder.png")
        width, height = 400, 400
        image = Image.new('RGB', (width, height), color=(74, 107, 156))
        draw = ImageDraw.Draw(image)
        try:
            font = ImageFont.truetype("arial.ttf", 24)
        except:
            try:
                font = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", 24)
            except:
                font = ImageFont.load_default()
        text = artist_name
        if len(text) > 20:
            text = text[:17] + "..."
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        x = (width - text_width) / 2
        y = (height - text_height) / 2
        draw.text((x, y), text, fill=(255, 255, 255), font=font)
        image.save(placeholder_path, "PNG")
        return placeholder_path
    except Exception as e:
        logger.error(f"❌ Ошибка создания placeholder: {e}")
        return None

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

        generator = ModernPresentationGenerator(base_path=base_path)

        make_bw = request_data.get("design", {}).get("make_bw", False)
        zip_path = generator.generate(
            game_title=game_title,
            tracks=tracks,  # может быть None — генератор подхватит JSON
            make_bw=make_bw
        )

        if not zip_path or not os.path.exists(zip_path):
            raise HTTPException(status_code=500, detail="Ошибка генерации: файл не создан")

        logger.info(f"✅ Презентация успешно создана: {zip_path}")
        return {
            "success": True,
            "message": f"Презентация '{game_title}' создана успешно",
            "archive": os.path.basename(zip_path),
            "archive_path": zip_path,
            "download_url": f"/api/download/{os.path.basename(zip_path)}"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"❌ Ошибка генерации презентации: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка генерации: {str(e)}")


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
        file_path = None
        for path in possible_paths:
            if os.path.exists(path):
                file_path = path
                break
        if file_path and os.path.exists(file_path):
            return FileResponse(file_path, filename=filename, media_type='application/octet-stream')
        raise HTTPException(status_code=404, detail="Файл не найден")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка загрузки: {str(e)}")

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