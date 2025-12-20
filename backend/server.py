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

class SegmentUpdate(BaseModel):
    start_time: float
    duration: float = 30

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

def parse_track_list(track_list_text: str) -> List[dict]:
    """
    Разбирает текстовый список треков на структурированные данные
    Специальная обработка для текста из WhatsApp на Mac
    """
    tracks = []
    
    # Разделяем текст на строки
    lines = track_list_text.strip().split('\n')
    
    for line_num, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue
        
        # КОМПЛЕКСНАЯ ОЧИСТКА ДЛЯ WHATSAPP + MAC
        # 1. Удаляем все невидимые символы форматирования
        invisible_chars = [
            '\u200b', '\u200c', '\u200d', '\u200e', '\u200f',  # Directional formatting
            '\u2060', '\u2061', '\u2062', '\u2063', '\u2064',  # Invisible operators
            '\ufeff', '\ufffc', '\ufffd',                     # BOM and specials
            '\u202a', '\u202b', '\u202c', '\u202d', '\u202e', # Bidirectional text
            '\u00a0', '\u1680', '\u180e',                     # No-break spaces
            '\u2000', '\u2001', '\u2002', '\u2003', '\u2004', # Various spaces
            '\u2005', '\u2006', '\u2007', '\u2008', '\u2009',
            '\u200a', '\u2028', '\u2029', '\u202f',
            '\u205f', '\u3000'
        ]
        
        for char in invisible_chars:
            line = line.replace(char, ' ')
        
        # 2. Убираем нумерацию в начале строки (1., 2., 01., и т.п.)
        line = re.sub(r'^\d+\.\s*', '', line)
        
        # 3. Заменяем множественные пробелы на один
        line = re.sub(r'\s+', ' ', line).strip()
            
        # 4. Ищем разделитель (поддерживаем разные типы дефисов и тире)
        separators = [' - ', ' — ', ' – ', ' – ', ' — ', '-', '–', '—']
        
        artist = 'Неизвестный исполнитель'
        title = 'Без названия'
        separator_found = False
        
        for sep in separators:
            if sep in line:
                parts = line.split(sep, 1)
                if len(parts) == 2:
                    artist = parts[0].strip()
                    title = parts[1].strip()
                    separator_found = True
                    break
        
        if not separator_found:
            # Если разделитель не найден, пробуем другие варианты
            if ' ' in line:
                # Пробуем разделить по первому пробелу (для формата "Артист Название")
                parts = line.split(' ', 1)
                if len(parts) == 2:
                    artist = parts[0].strip()
                    title = parts[1].strip()
            else:
                # Вся строка как артист
                artist = line
                title = 'Без названия'
        
        # 5. ФИНАЛЬНАЯ ОЧИСТКА
        artist = re.sub(r'[^\w\sа-яА-ЯёЁ\-&]', '', artist).strip()
        title = re.sub(r'[^\w\sа-яА-ЯёЁ\-&]', '', title).strip()
        
        # 6. Убираем оставшиеся нестандартные символы
        artist = ''.join(char for char in artist if ord(char) >= 32 or char in ['\n', '\t'])
        title = ''.join(char for char in title if ord(char) >= 32 or char in ['\n', '\t'])
        
        if artist or title:
            tracks.append({
                'artist': artist if artist else 'Неизвестный исполнитель',
                'title': title if title else 'Без названия',
                'original_line': line,
                'line_number': line_num,
                'cleaned': True  # Флаг что строка была очищена
            })
    
    logger.info(f"📝 Разобрано {len(tracks)} треков из {len(lines)} строк (WhatsApp/Mac)")
    
    # Дополнительная отладка
    if tracks:
        logger.info("🔍 Примеры распознанных треков:")
        for i, track in enumerate(tracks[:3]):
            logger.info(f"   {i+1}. '{track['artist']}' - '{track['title']}'")
    
    return tracks

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
# YANDEX TOKEN MANAGEMENT API
# =========================

YANDEX_TOKEN_FILE = os.path.join(BASE_DIR, "config", "yandex_token.txt")

def save_yandex_token(token):
    """Сохранить Яндекс токен в файл"""
    try:
        config_dir = os.path.dirname(YANDEX_TOKEN_FILE)
        os.makedirs(config_dir, exist_ok=True)
        
        with open(YANDEX_TOKEN_FILE, 'w', encoding='utf-8') as f:
            f.write(token.strip())
        
        logger.info("✅ Яндекс токен сохранен")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения Яндекс токена: {e}")
        return False

def load_yandex_token():
    """Загрузить Яндекс токен из файла"""
    try:
        if os.path.exists(YANDEX_TOKEN_FILE):
            with open(YANDEX_TOKEN_FILE, 'r', encoding='utf-8') as f:
                token = f.read().strip()
                if token:
                    logger.info("✅ Яндекс токен загружен из файла")
                    return token
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки Яндекс токена: {e}")
    
    return None

def get_yandex_token_status():
    """Проверить статус Яндекс токена"""
    token = load_yandex_token()
    if not token:
        return {
            "has_token": False,
            "is_valid": False,
            "message": "Токен не установлен"
        }
    
    # Проверяем валидность токена
    try:
        from yandex_music import Client
        client = Client(token).init()
        # Простая проверка - пытаемся получить информацию об аккаунте
        account = client.account_status()
        return {
            "has_token": True,
            "is_valid": True,
            "message": "✅ Токен действителен",
            "account_info": {
                "login": account.account.login,
                "uid": account.account.uid
            }
        }
    except Exception as e:
        logger.warning(f"⚠️ Яндекс токен недействителен: {e}")
        return {
            "has_token": True,
            "is_valid": False,
            "message": f"❌ Токен недействителен: {str(e)}"
        }

@app.get("/api/yandex/token/status")
async def get_yandex_token_status_endpoint():
    """Получить статус Яндекс токена"""
    try:
        status = get_yandex_token_status()
        return {
            "success": True,
            "status": status
        }
    except Exception as e:
        logger.error(f"❌ Ошибка проверки статуса токена: {e}")
        return {
            "success": False,
            "error": str(e)
        }

@app.post("/api/yandex/token/save")
async def save_yandex_token_endpoint(request_data: dict):
    """Сохранить Яндекс токен"""
    try:
        token = request_data.get('token', '').strip()
        if not token:
            return {
                "success": False,
                "error": "Токен не может быть пустым"
            }
        
        # Проверяем валидность токена
        try:
            from yandex_music import Client
            client = Client(token).init()
            # Быстрая проверка
            client.account_status()
        except Exception as e:
            return {
                "success": False,
                "error": f"Недействительный токен: {str(e)}"
            }
        
        # Сохраняем токен
        if save_yandex_token(token):
            return {
                "success": True,
                "message": "✅ Яндекс токен успешно сохранен и проверен"
            }
        else:
            return {
                "success": False,
                "error": "Ошибка сохранения токена"
            }
            
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения Яндекс токена: {e}")
        return {
            "success": False,
            "error": str(e)
        }

@app.delete("/api/yandex/token/delete")
async def delete_yandex_token():
    """Удалить Яндекс токен"""
    try:
        if os.path.exists(YANDEX_TOKEN_FILE):
            os.remove(YANDEX_TOKEN_FILE)
            logger.info("🗑️ Яндекс токен удален")
            return {
                "success": True,
                "message": "✅ Яндекс токен удален"
            }
        else:
            return {
                "success": False,
                "error": "Токен не найден"
            }
    except Exception as e:
        logger.error(f"❌ Ошибка удаления Яндекс токена: {e}")
        return {
            "success": False,
            "error": str(e)
        }

# =========================
# ADDITIONAL TRACKS ENDPOINTS FOR COMPATIBILITY
# =========================

@app.get("/api/tracks/list")
async def get_tracks_list():
    """Алиас для /api/tracks для совместимости"""
    return await get_tracks()

@app.get("/api/tracks/all")
async def get_tracks_all():
    """Алиас для /api/tracks для совместимости"""
    return await get_tracks()

@app.get("/api/media/tracks")
async def get_media_tracks():
    """Алиас для /api/tracks для совместимости"""
    return await get_tracks()

@app.get("/api/library/tracks")
async def get_library_tracks():
    """Алиас для /api/tracks для совместимости"""
    return await get_tracks()

# =========================
# YANDEX MUSIC & YOUTUBE DOWNLOAD - БЕЗОПАСНАЯ ПОСЛЕДОВАТЕЛЬНАЯ ВЕРСИЯ
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
        download_status["successful_tracks"] = [r for r in results if r.get('success')]
        download_status["duplicate_tracks"] = [r for r in results if r.get('duplicate')]
        download_status["failed_tracks"] = [r for r in results if not r.get('success') and not r.get('duplicate')]

async def download_single_track_from_youtube(track_info: dict):
    """БЫСТРЫЙ скачивальщик с YouTube"""
    artist = track_info.get("artist", "")
    title = track_info.get("title", "")
    
    logger.info(f"🎵 YouTube: {artist} - {title}")
    
    # БЫСТРАЯ ПРОВЕРКА ДУБЛИКАТА
    if media_library.track_exists(artist, title):
        existing_track = media_library.get_track_by_artist_title(artist, title)
        return {
            "success": False, 
            "error": f"Трек уже существует (ID: {existing_track['id']})",
            "artist": artist,
            "title": title,
            "duplicate": True,
            "existing_track_id": existing_track['id']
        }
    
    try:
        import yt_dlp
        
        # Создаем имя файла
        safe_artist = "".join(c for c in artist if c.isalnum() or c in (' ', '-', '_')).strip()
        safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip()
        filename_safe = f"{safe_artist} - {safe_title}.mp3"
        
        downloads_dir = os.path.join(BASE_DIR, "downloads")
        os.makedirs(downloads_dir, exist_ok=True)
        final_path = os.path.join(downloads_dir, filename_safe)
        
        # БЫСТРАЯ ПРОВЕРКА существования файла
        if os.path.exists(final_path):
            file_size = os.path.getsize(final_path)
            if file_size > 0 and file_size < 50 * 1024 * 1024:
                if media_library.track_exists(artist, title):
                    existing_track = media_library.get_track_by_artist_title(artist, title)
                    return {
                        "success": False, 
                        "error": f"Трек уже добавлен (ID: {existing_track['id']})",
                        "artist": artist,
                        "title": title,
                        "duplicate": True
                    }
        
               
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': final_path.replace('.mp3', ''),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'noplaylist': True,
            'no_warnings': True,
            'quiet': False,  # временно для логов
            'socket_timeout': 25,
            'retries': 3,
            'fragment_retries': 10,
            'extractaudio': True,
            'audioformat': 'mp3',
            'nocheckcertificate': True,
            'ignoreerrors': False,
            'logtostderr': False,
            'no_color': True,
            'http_chunk_size': 5242880,
            'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36'
        }
        
        search_query = f"{artist} {title}"
        
        def _sync_youtube_download():
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    search_results = ydl.extract_info(f"ytsearch1:{search_query}", download=False)
                    
                    if not search_results or 'entries' not in search_results or not search_results['entries']:
                        return None, "Трек не найден"
                    
                    video_info = search_results['entries'][0]
                    video_url = video_info.get('webpage_url')
                    
                    if not video_url:
                        return None, "Не удалось получить ссылку"
                    
                    ydl.download([video_url])
                    return final_path, None
                    
            except Exception as e:
                error_msg = str(e)
                return None, f"Ошибка: {error_msg}"

        # Запускаем скачивание с коротким таймаутом
        loop = asyncio.get_event_loop()
        try:
            downloaded_path, download_error = await asyncio.wait_for(
                loop.run_in_executor(None, _sync_youtube_download),
                timeout=75  # 1 минута максимум
            )
        except asyncio.TimeoutError:
            return {
                "success": False, 
                "error": "Таймаут при скачивании с YouTube",
                "artist": artist,
                "title": title
            }
        
        if download_error:
            return {
                "success": False, 
                "error": download_error,
                "artist": artist,
                "title": title
            }
        
        if not os.path.exists(final_path):
            return {
                "success": False, 
                "error": "Файл не был создан",
                "artist": artist,
                "title": title
            }
        
        # Быстрая проверка файла
        file_size = os.path.getsize(final_path)
        if file_size == 0 or file_size > 40 * 1024 * 1024:
            if os.path.exists(final_path):
                os.remove(final_path)
            return {
                "success": False, 
                "error": "Файл невалидный",
                "artist": artist,
                "title": title
            }
        
        # Быстрое добавление в медиатеку
        result = media_library.add_track(final_path, filename_safe, {
            "artist": artist,
            "title": title,
            "source": "youtube"
        })
        
        if not result.get('success'):
            if result.get('error') == 'duplicate':
                existing_track = result.get('existing_track')
                return {
                    "success": False, 
                    "error": f"Трек уже существует (ID: {existing_track['id']})",
                    "artist": artist,
                    "title": title,
                    "duplicate": True
                }
            else:
                return {
                    "success": False, 
                    "error": "Ошибка добавления в медиатеку",
                    "artist": artist,
                    "title": title
                }
        
        track = result['track']
        track_id = track["id"]
        
        # ОТЛОЖЕННЫЕ ОПЕРАЦИИ (не блокируем скачивание)
        async def background_tasks():
            try:
                # Анализ сегмента
                segment_result = audio_editor.suggest_best_segment(final_path)
                if segment_result is not None:
                    media_library.update_track_segment(track_id, segment_result, 30)
                
                # Поиск фото
                photo_path = image_searcher.fetch_artist_png(artist, track_id)
                if photo_path and os.path.exists(photo_path):
                    media_library.update_track(track_id, {"image_path": photo_path})
            except Exception as e:
                pass  # Игнорируем ошибки в фоновых задачах
        
        asyncio.create_task(background_tasks())
        
        return {
            "success": True, 
            "file_path": final_path, 
            "track_id": track_id, 
            "artist": artist,
            "title": title,
            "filename": filename_safe,
            "source": "youtube"
        }
        
    except Exception as e:
        return {
            "success": False, 
            "error": f"Ошибка YouTube: {str(e)}",
            "artist": artist,
            "title": title
        }

async def try_yandex_music(track_info: dict):
    """Попытка скачать с Яндекс.Музыки"""
    artist = track_info.get("artist", "")
    title = track_info.get("title", "")
    
    try:
        from yandex_music import Client as YandexClient
        
        def _sync_search():
            try:
                saved_token = load_yandex_token()
                YANDEX_MUSIC_TOKEN = saved_token or "y0__xC-3q2iAxje-AYglImpghUw9pW0kAgCx0SZ5vnWcYWpiGpLqwVPsGWEfg"
                
                client = YandexClient(YANDEX_MUSIC_TOKEN).init()
                search_result = client.search(f"{artist} {title}")
                
                if not search_result or not search_result.best:
                    return None, "Трек не найден"
                
                best = search_result.best
                if not hasattr(best, 'type') or best.type != 'track':
                    return None, "Не трек"
                
                track = best.result
                if not track:
                    return None, "Трек не найден"
                
                download_info_list = track.get_download_info()
                if not download_info_list:
                    return None, "Нет ссылок для скачивания"
                
                # Ищем MP3 или любой доступный формат
                best_download_info = None
                for download_info in download_info_list:
                    codec = getattr(download_info, 'codec', '').lower()
                    if codec == 'mp3':
                        best_download_info = download_info
                        break
                    elif not best_download_info:
                        best_download_info = download_info
                
                if not best_download_info:
                    return None, "Нет подходящих форматов"
                
                direct_link = best_download_info.get_direct_link()
                if not direct_link:
                    return None, "Не удалось получить ссылку"
                
                return direct_link, None
                
            except Exception as e:
                return None, f"Ошибка Яндекс: {str(e)}"

        # Быстрый поиск с таймаутом
        loop = asyncio.get_event_loop()
        try:
            mp3_url, search_error = await asyncio.wait_for(
                loop.run_in_executor(None, _sync_search),
                timeout=15  # Всего 15 секунд на поиск в Яндекс
            )
        except asyncio.TimeoutError:
            return {"success": False, "error": "Таймаут Яндекс"}
        
        if search_error or not mp3_url:
            return {"success": False, "error": search_error or "Неизвестная ошибка Яндекс"}

        # Скачивание файла
        safe_artist = "".join(c for c in artist if c.isalnum() or c in (' ', '-', '_')).strip()
        safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip()
        filename_safe = f"{safe_artist} - {safe_title}.mp3"
        
        downloads_dir = os.path.join(BASE_DIR, "downloads")
        final_path = os.path.join(downloads_dir, filename_safe)

        # Скачиваем с таймаутом
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            async with session.get(mp3_url) as resp:
                if resp.status != 200:
                    return {"success": False, "error": "Ошибка скачивания"}
                
                with open(final_path, "wb") as f:
                    async for chunk in resp.content.iter_chunked(65536):  # 64KB chunks
                        f.write(chunk)

        # Быстрая проверка файла
        file_size = os.path.getsize(final_path)
        if file_size == 0 or file_size > 40 * 1024 * 1024:
            os.remove(final_path)
            return {"success": False, "error": "Файл невалидный"}

        # Добавляем в медиатеку
        result = media_library.add_track(final_path, filename_safe, {
            "artist": artist,
            "title": title,
            "source": "yandex_music"
        })
        
        if not result.get('success'):
            if result.get('error') == 'duplicate':
                return {"success": False, "error": "Дубликат", "duplicate": True}
            return {"success": False, "error": "Ошибка добавления"}
        
        track = result['track']
        
        # Фоновые задачи
        async def background_tasks():
            try:
                segment_result = audio_editor.suggest_best_segment(final_path)
                if segment_result is not None:
                    media_library.update_track_segment(track['id'], segment_result, 30)
                
                photo_path = image_searcher.fetch_artist_png(artist, track['id'])
                if photo_path:
                    media_library.update_track(track['id'], {"image_path": photo_path})
            except Exception:
                pass
        
        asyncio.create_task(background_tasks())
        
        return {
            "success": True, 
            "file_path": final_path, 
            "track_id": track['id'], 
            "artist": artist,
            "title": title,
            "filename": filename_safe,
            "source": "yandex_music"
        }
        
    except Exception as e:
        return {"success": False, "error": f"Ошибка Яндекс: {str(e)}"}

async def try_hitmotop(track_info: dict):
    """Попытка скачать с hitmotop.com"""
    artist = track_info.get("artist", "")
    title = track_info.get("title", "")
    
    try:
        import aiohttp
        from bs4 import BeautifulSoup
        
        # Кодируем поисковый запрос
        search_query = f"{artist} {title}"
        encoded_query = requests.utils.quote(search_query)
        search_url = f"https://rus.hitmotop.com/search?q={encoded_query}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
            # Получаем страницу поиска
            async with session.get(search_url, headers=headers) as response:
                if response.status != 200:
                    return {"success": False, "error": f"Ошибка HTTP {response.status}"}
                
                html = await response.text()
        
        # Парсим HTML
        soup = BeautifulSoup(html, 'html.parser')
        
        # Ищем треки
        track_elements = soup.find_all('li', class_='tracks__item')
        
        if not track_elements:
            return {"success": False, "error": "Треки не найдены на странице"}
        
        # Ищем подходящий трек
        mp3_url = None
        for track_element in track_elements:
            try:
                # Извлекаем данные из data-musmeta
                musmeta = track_element.get('data-musmeta')
                if musmeta:
                    import json
                    track_data = json.loads(musmeta)
                    
                    track_artist = track_data.get('artist', '').lower()
                    track_title = track_data.get('title', '').lower()
                    
                    # Проверяем совпадение артиста и названия
                    if (artist.lower() in track_artist or track_artist in artist.lower()) and \
                       (title.lower() in track_title or track_title in title.lower()):
                        
                        # Пробуем получить прямую ссылку на MP3
                        download_btn = track_element.find('a', class_='track__download-btn')
                        if download_btn and download_btn.get('href'):
                            mp3_url = download_btn.get('href')
                            break
                        
                        # Или из data-musmeta
                        if track_data.get('url'):
                            mp3_url = track_data.get('url')
                            break
            
            except Exception as e:
                continue
        
        if not mp3_url:
            return {"success": False, "error": "Ссылка на MP3 не найдена"}
        
        # Скачиваем MP3 файл
        safe_artist = "".join(c for c in artist if c.isalnum() or c in (' ', '-', '_')).strip()
        safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip()
        filename_safe = f"{safe_artist} - {safe_title}.mp3"
        
        downloads_dir = os.path.join(BASE_DIR, "downloads")
        os.makedirs(downloads_dir, exist_ok=True)
        final_path = os.path.join(downloads_dir, filename_safe)
        
        # Скачиваем файл
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            async with session.get(mp3_url, headers=headers) as resp:
                if resp.status != 200:
                    return {"success": False, "error": f"Ошибка скачивания MP3: {resp.status}"}
                
                with open(final_path, "wb") as f:
                    async for chunk in resp.content.iter_chunked(65536):
                        f.write(chunk)
        
        # Проверяем файл
        file_size = os.path.getsize(final_path)
        if file_size == 0 or file_size > 40 * 1024 * 1024:
            if os.path.exists(final_path):
                os.remove(final_path)
            return {"success": False, "error": "Файл невалидный"}
        
        # Добавляем в медиатеку
        result = media_library.add_track(final_path, filename_safe, {
            "artist": artist,
            "title": title,
            "source": "hitmotop"
        })
        
        if not result.get('success'):
            if result.get('error') == 'duplicate':
                return {"success": False, "error": "Дубликат", "duplicate": True}
            return {"success": False, "error": "Ошибка добавления в медиатеку"}
        
        track = result['track']
        
        # Фоновые задачи
        async def background_tasks():
            try:
                segment_result = audio_editor.suggest_best_segment(final_path)
                if segment_result is not None:
                    media_library.update_track_segment(track['id'], segment_result, 30)
                
                photo_path = image_searcher.fetch_artist_png(artist, track['id'])
                if photo_path:
                    media_library.update_track(track['id'], {"image_path": photo_path})
            except Exception:
                pass
        
        asyncio.create_task(background_tasks())
        
        return {
            "success": True, 
            "file_path": final_path, 
            "track_id": track['id'], 
            "artist": artist,
            "title": title,
            "filename": filename_safe,
            "source": "hitmotop"
        }
        
    except Exception as e:
        return {"success": False, "error": f"Ошибка Hitmotop: {str(e)}"}

async def download_track_with_priority(track_info: dict):
    """Скачивание трека по приоритету: Яндекс → Hitmotop → YouTube"""
    artist = track_info.get("artist", "")
    title = track_info.get("title", "")
    
    # СНАЧАЛА проверяем дубликат
    if media_library.track_exists(artist, title):
        existing_track = media_library.get_track_by_artist_title(artist, title)
        return {
            "success": False, 
            "error": f"Трек уже существует (ID: {existing_track['id']})",
            "artist": artist,
            "title": title,
            "duplicate": True
        }
    
    # 1. ПРОБУЕМ Яндекс.Музыку
    logger.info(f"🎵 1. Пробуем Яндекс: {artist} - {title}")
    yandex_result = await try_yandex_music(track_info)
    
    if yandex_result.get('success'):
        logger.info(f"✅ Яндекс успех: {artist} - {title}")
        return yandex_result
    
    # 2. ПРОБУЕМ Hitmotop
    logger.info(f"🎵 2. Яндекс не сработал, пробуем Hitmotop: {artist} - {title}")
    hitmotop_result = await try_hitmotop(track_info)
    
    if hitmotop_result.get('success'):
        logger.info(f"✅ Hitmotop успех: {artist} - {title}")
        return hitmotop_result
    
    # 3. ПРОБУЕМ YouTube
    logger.info(f"🎵 3. Hitmotop не сработал, пробуем YouTube: {artist} - {title}")
    youtube_result = await download_single_track_from_youtube(track_info)
    
    if youtube_result.get('success'):
        logger.info(f"✅ YouTube успех: {artist} - {title}")
    else:
        logger.error(f"❌ Все источники провалились: {artist} - {title}")
    
    return youtube_result

@app.post("/api/tracks/download-from-list")
async def download_tracks_from_list(request_data: dict):
    """БЕЗОПАСНОЕ последовательное скачивание треков: Яндекс → Hitmotop → YouTube (без параллелизма)"""
    global download_status
    try:
        track_list_text = request_data.get('track_list', '')
        if not track_list_text.strip():
            raise HTTPException(status_code=400, detail="Список треков пуст")

        tracks_to_download = parse_track_list(track_list_text)
        if not tracks_to_download:
            raise HTTPException(status_code=400, detail="Не удалось распознать список треков")

        logger.info(f"🎵 Начинаем БЕЗОПАСНОЕ последовательное скачивание {len(tracks_to_download)} треков")

        # Инициализируем статус
        download_status.update({
            "is_running": True,
            "total": len(tracks_to_download),
            "current": 0,
            "current_track": "Подготовка...",
            "results": [],
            "failed_tracks": [],
            "duplicate_tracks": [],
            "successful_tracks": [],
            "source": "auto"
        })

        all_results = []

        for i, track_info in enumerate(tracks_to_download):
            current_index = i + 1
            artist = track_info.get("artist", "")
            title = track_info.get("title", "")
            current_track_str = f"{artist} - {title}"
            logger.info(f"🔄 [{current_index}/{len(tracks_to_download)}] Обработка: {current_track_str}")

            # Обновляем статус перед обработкой
            download_status["current"] = current_index
            download_status["current_track"] = f"Обработка: {current_index}/{len(tracks_to_download)} — {current_track_str}"

            # === 1. Пробуем Яндекс.Музыку ===
            logger.info(f"🎵 1. Пробуем Яндекс: {current_track_str}")
            await asyncio.sleep(2.5)  # Задержка для обхода rate-limit
            result = await try_yandex_music(track_info)
            if result.get('success'):
                logger.info(f"✅ Успех (yandex_music): {current_track_str}")
                all_results.append(result)
                continue

            # === 2. Пробуем Hitmotop ===
            logger.info(f"🎵 2. Пробуем Hitmotop: {current_track_str}")
            result = await try_hitmotop(track_info)
            if result.get('success'):
                logger.info(f"✅ Успех (hitmotop): {current_track_str}")
                all_results.append(result)
                continue

            # === 3. Пробуем YouTube (только если всё выше провалилось) ===
            logger.info(f"🎵 3. Пробуем YouTube: {current_track_str}")
            result = await download_single_track_from_youtube(track_info)
            if result.get('success'):
                logger.info(f"✅ Успех (youtube): {current_track_str}")
            else:
                logger.error(f"❌ Все источники провалились: {current_track_str}")

            all_results.append(result)

            # Обновляем статус после каждого трека
            download_status["results"] = all_results
            download_status["successful_tracks"] = [r for r in all_results if r.get('success')]
            download_status["duplicate_tracks"] = [r for r in all_results if r.get('duplicate')]
            download_status["failed_tracks"] = [r for r in all_results if not r.get('success') and not r.get('duplicate')]

        # Финальная статистика
        successful_results = [r for r in all_results if r.get('success')]
        sources_stats = {}
        for result in successful_results:
            src = result.get('source', 'unknown')
            sources_stats[src] = sources_stats.get(src, 0) + 1

        successful_count = len(successful_results)
        duplicate_count = len([r for r in all_results if r.get('duplicate')])
        failed_count = len([r for r in all_results if not r.get('success') and not r.get('duplicate')])

        download_status.update({
            "is_running": False,
            "current": len(tracks_to_download),
            "current_track": f"Завершено: {successful_count} успешно, {duplicate_count} дубликатов, {failed_count} ошибок",
            "results": all_results,
            "successful_tracks": successful_results,
            "duplicate_tracks": [r for r in all_results if r.get('duplicate')],
            "failed_tracks": [r for r in all_results if not r.get('success') and not r.get('duplicate')],
            "sources_stats": sources_stats
        })

        logger.info(f"🎉 Скачивание завершено: {successful_count} успешно, {duplicate_count} дубликатов, {failed_count} ошибок")
        logger.info(f"📊 Источники: {sources_stats}")

        return {
            "success": True,
            "message": f"Обработано {len(all_results)} треков",
            "results": all_results,
            "downloaded": successful_count,
            "duplicates": duplicate_count,
            "failed": failed_count,
            "source": "auto",
            "sources_stats": sources_stats,
            "statistics": {
                "total": len(tracks_to_download),
                "successful": successful_count,
                "duplicates": duplicate_count,
                "failed": failed_count,
                "success_rate": round((successful_count / len(tracks_to_download)) * 100, 1) if tracks_to_download else 0
            }
        }

    except Exception as e:
        logger.error(f"❌ Критическая ошибка скачивания: {e}")
        download_status.update({
            "is_running": False,
            "current_track": f"Критическая ошибка: {str(e)}"
        })
        raise HTTPException(status_code=500, detail=f"Критическая ошибка: {str(e)}")

# =========================
# TRACK ID MANAGEMENT API
# =========================

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

@app.post("/api/tracks/reorder-by-ids")
async def reorder_tracks_by_ids(request: dict):
    """Переупорядочить треки по переданному списку ID с ОБНОВЛЕНИЕМ ФОТО"""
    track_ids = request.get("track_ids")
    if not isinstance(track_ids, list):
        raise HTTPException(status_code=400, detail="track_ids должен быть списком")
    
    # ВАЖНО: Используем новую функцию с обновлением фото
    if media_library.reorder_tracks_with_photo_fix(track_ids):
        return {
            "success": True, 
            "message": f"Переупорядочено {len(track_ids)} треков с обновлением фото"
        }
    
    raise HTTPException(status_code=500, detail="Не удалось переупорядочить треки")
@app.post("/api/tracks/fix-broken-photos")
async def fix_broken_photos():
    """Исправить сломанные пути к фото артистов"""
    try:
        result = media_library.fix_broken_image_paths()
        return {
            "success": True,
            "message": result['message'],
            "fixed_count": result['fixed_count'],
            "broken_tracks": result['broken_tracks']
        }
    except Exception as e:
        logger.error(f"❌ Ошибка исправления фото: {e}")
        return {
            "success": False,
            "error": str(e)
        }
# =========================
# TRACK MANAGEMENT API
# =========================

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
    """Удалить конкретный трек с очисткой кеша его фото"""
    try:
        # Сначала получаем информацию о треке для логирования
        track = media_library.get_track(track_id)
        artist_name = track.get('artist', 'Unknown') if track else 'Unknown'
        
        result = media_library.delete_track(track_id)
        if result.get('success'):
            # ОЧИСТКА КЕША ФОТО ДЛЯ ЭТОГО АРТИСТА
            cache_key_to_remove = f"{artist_name.lower()}_{track_id}"
            if cache_key_to_remove in image_searcher.artist_cache:
                del image_searcher.artist_cache[cache_key_to_remove]
                logger.info(f"🧹 Удален кеш фото для трека {track_id} ({artist_name})")
            
            # Также пытаемся удалить связанное фото файла
            try:
                image_path = track.get('image_path')
                if image_path and os.path.exists(image_path):
                    os.remove(image_path)
                    logger.info(f"🗑️ Удален файл фото: {image_path}")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось удалить файл фото: {e}")
            
            return {
                "message": "Трек удален", 
                "files_removed": result.get('files_removed', []),
                "cache_cleared": True,
                "artist": artist_name
            }
        raise HTTPException(status_code=404, detail="Трек не найден")
    except Exception as e:
        logger.error(f"❌ Ошибка удаления трека {track_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка удаления: {str(e)}")

@app.delete("/api/tracks")
async def clear_tracks():
    """Очистить всю медиатеку с полной очисткой кеша фото"""
    try:
        # Получаем информацию о треках перед удалением для логирования
        tracks_before = media_library.get_tracks()
        artists_count = len(set(track.get('artist', '') for track in tracks_before))
        
        result = media_library.clear()
        if result.get('success'):
            # ПОЛНАЯ ОЧИСТКА КЕША ФОТО
            cache_size_before = len(image_searcher.artist_cache)
            image_searcher.artist_cache.clear()
            
            # Очистка файлов фото в папке images
            images_cleared = clear_track_images_folder()
            
            logger.info(f"🧹 Медиатека очищена: {len(tracks_before)} треков, " +
                       f"кеш фото очищен ({cache_size_before} записей), " +
                       f"файлов фото удалено: {images_cleared}")
            
            return {
                "message": "Медиатека полностью очищена", 
                "tracks_deleted": result.get('tracks_deleted', 0),
                "files_removed": result.get('files_removed', []),
                "cache_cleared": cache_size_before,
                "images_cleared": images_cleared,
                "artists_affected": artists_count
            }
        raise HTTPException(status_code=500, detail="Ошибка очистки медиатеки")
    except Exception as e:
        logger.error(f"❌ Ошибка очистки медиатеки: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка очистки: {str(e)}")

def clear_track_images_folder():
    """Очистить папку с фото треков (оставляет только backup и системные файлы)"""
    try:
        images_dir = os.path.join(BASE_DIR, "images")
        if not os.path.exists(images_dir):
            return 0
            
        deleted_count = 0
        for filename in os.listdir(images_dir):
            if filename.endswith('_artist.png'):
                file_path = os.path.join(images_dir, filename)
                try:
                    os.remove(file_path)
                    deleted_count += 1
                    logger.debug(f"🗑️ Удален файл фото: {filename}")
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось удалить {filename}: {e}")
        
        return deleted_count
    except Exception as e:
        logger.error(f"❌ Ошибка очистки папки images: {e}")
        return 0
@app.post("/api/tracks/delete-batch")
async def delete_tracks_batch(request: dict):
    """Массовое удаление треков с очисткой кеша"""
    try:
        track_ids = request.get("track_ids", [])
        if not track_ids:
            raise HTTPException(status_code=400, detail="Список ID треков пуст")
        
        deleted_count = 0
        cache_cleared_count = 0
        errors = []
        
        for track_id in track_ids:
            try:
                track = media_library.get_track(track_id)
                if track:
                    # Удаляем трек
                    result = media_library.delete_track(track_id)
                    if result.get('success'):
                        deleted_count += 1
                        
                        # Очищаем кеш фото для этого трека
                        artist_name = track.get('artist', 'Unknown')
                        cache_key = f"{artist_name.lower()}_{track_id}"
                        if cache_key in image_searcher.artist_cache:
                            del image_searcher.artist_cache[cache_key]
                            cache_cleared_count += 1
                            
                        # Удаляем файл фото
                        image_path = track.get('image_path')
                        if image_path and os.path.exists(image_path):
                            try:
                                os.remove(image_path)
                            except:
                                pass
                    else:
                        errors.append(f"Трек {track_id}: ошибка удаления")
                else:
                    errors.append(f"Трек {track_id}: не найден")
                    
            except Exception as e:
                errors.append(f"Трек {track_id}: {str(e)}")
        
        logger.info(f"🧹 Массовое удаление: {deleted_count} треков, " +
                   f"очищено {cache_cleared_count} записей кеша, " +
                   f"ошибок: {len(errors)}")
        
        return {
            "success": True,
            "deleted_count": deleted_count,
            "cache_cleared": cache_cleared_count,
            "errors": errors,
            "message": f"Удалено {deleted_count} треков, очищено {cache_cleared_count} записей кеша"
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка массового удаления треков: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка массового удаления: {str(e)}")
# =========================
# ARTIST PHOTOS API - ИСПРАВЛЕННАЯ ВЕРСИЯ С ОБРАБОТКОЙ ОШИБОК
# =========================

@app.get("/api/tracks/{track_id}/artist-photo")
async def get_artist_photo(track_id: int):
    """Получить фото артиста для трека с обработкой ошибок и плейсхолдером"""
    try:
        track = media_library.get_track(track_id)
        if not track:
            logger.warning(f"⚠️ Трек {track_id} не найден при запросе фото")
            # Возвращаем плейсхолдер вместо ошибки
            return await get_artist_placeholder(track_id, "Трек не найден")
        
        image_path = track.get('image_path')
        
        # Если путь есть и файл существует - возвращаем фото
        if image_path and os.path.exists(image_path):
            logger.info(f"✅ Отдаем фото для трека {track_id}: {image_path}")
            return FileResponse(
                image_path,
                media_type='image/png',
                filename=f"artist_{track_id}.png"
            )
        
        # Если фото нет, возвращаем плейсхолдер
        logger.warning(f"⚠️ Фото не найдено для трека {track_id}, используем плейсхолдер")
        artist_name = track.get('artist', 'Неизвестный артист')
        return await get_artist_placeholder(track_id, artist_name)

    except Exception as e:
        logger.error(f"❌ Ошибка получения фото для трека {track_id}: {e}")
        # Возвращаем плейсхолдер при любой ошибке
        return await get_artist_placeholder(track_id, f"Ошибка: {str(e)}")

async def get_artist_placeholder(track_id: int, artist_name: str):
    """Создать плейсхолдер изображение для артиста"""
    try:
        from PIL import Image, ImageDraw, ImageFont
        import io
        
        # Создаем изображение 400x400
        img = Image.new('RGB', (400, 400), color=(102, 126, 234))  # Красивый синий
        d = ImageDraw.Draw(img)
        
        # Пробуем использовать шрифт (если доступен)
        try:
            font = ImageFont.truetype("arial.ttf", 24)
        except:
            try:
                font = ImageFont.truetype("Arial.ttf", 24)
            except:
                font = ImageFont.load_default()
        
        # Обрезаем длинное имя артиста
        display_name = artist_name[:20] + "..." if len(artist_name) > 20 else artist_name
        
        # Рисуем текст
        text = f"Артист:\n{display_name}"
        bbox = d.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        x = (400 - text_width) / 2
        y = (400 - text_height) / 2
        
        d.text((x, y), text, fill=(255, 255, 255), font=font)
        
        # Сохраняем в буфер
        img_buffer = io.BytesIO()
        img.save(img_buffer, format='PNG')
        img_buffer.seek(0)
        
        # Создаем временный файл для плейсхолдера
        temp_dir = os.path.join(BASE_DIR, "temp")
        os.makedirs(temp_dir, exist_ok=True)
        placeholder_path = os.path.join(temp_dir, f"placeholder_{track_id}.png")
        img.save(placeholder_path, 'PNG')
        
        logger.info(f"🎨 Создан плейсхолдер для трека {track_id}: {artist_name}")
        return FileResponse(placeholder_path, media_type='image/png')
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка создания плейсхолдера: {e}")
        # Возвращаем простой текстовый ответ как последнее средство
        from fastapi.responses import Response
        return Response(
            content="Placeholder image error", 
            status_code=500,
            media_type="text/plain"
        )

@app.get("/api/tracks/{track_id}/artist-photo-or-placeholder")
async def get_artist_photo_with_fallback(track_id: int):
    """Безопасное получение фото артиста с автоматическим fallback"""
    try:
        # Сначала пробуем получить настоящее фото
        return await get_artist_photo(track_id)
    except Exception as e:
        logger.error(f"❌ Полный сбой получения фото для {track_id}: {e}")
        # Крайний fallback - возвращаем простой JSON
        return JSONResponse(
            status_code=200,
            content={
                "success": False,
                "message": "Фото недоступно",
                "track_id": track_id,
                "fallback": True
            }
        )

@app.post("/api/tracks/{track_id}/search-artist-photo")
async def search_artist_photo(track_id: int, request_data: dict):
    """Поиск фото артиста с обработкой ошибок"""
    try:
        track = media_library.get_track(track_id)
        if not track:
            return JSONResponse(
                status_code=404,
                content={"success": False, "error": "Трек не найден"}
            )
        
        artist_name = request_data.get('artist', track.get('artist', ''))
        get_multiple = request_data.get('get_multiple', True)
        
        if not artist_name:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "Имя артиста не указано"}
            )
        
        if get_multiple:
            photo_urls = image_searcher.fetch_multiple_artist_photos(artist_name, count=10)
        else:
            single_photo_path = image_searcher.fetch_artist_png(artist_name, track_id)
            photo_urls = [single_photo_path] if single_photo_path else []

        if photo_urls:
            return {
                "success": True, 
                "message": f"Найдено {len(photo_urls)} фото",
                "photos": photo_urls, 
                "artist": artist_name, 
                "count": len(photo_urls)
            }
        
        return {
            "success": False, 
            "message": "Не удалось найти фото артиста",
            "photos": [],
            "artist": artist_name
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка поиска фото: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": f"Ошибка поиска фото: {str(e)}"}
        )

@app.post("/api/tracks/{track_id}/upload-artist-photo")
async def upload_artist_photo(track_id: int, photo: UploadFile = File(...)):
    """Загрузить фото артиста и применить ко ВСЕМ трекам этого артиста"""
    try:
        logger.info(f"🖼️ Загрузка фото для трека {track_id}")
        
        track = media_library.get_track(track_id)
        if not track:
            logger.error(f"❌ Трек {track_id} не найден")
            return JSONResponse(
                status_code=404,
                content={"success": False, "error": "Трек не найден"}
            )

        if not photo.content_type or not photo.content_type.startswith('image/'):
            logger.error(f"❌ Файл не является изображением: {photo.content_type}")
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "Файл должен быть изображением"}
            )

        # Получаем имя артиста из трека
        artist_name = track.get('artist', '').strip()
        if not artist_name:
            logger.error(f"❌ Имя артиста не указано для трека {track_id}")
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "Имя артиста не указано в треке"}
            )

        # Скачиваем файл
        image_data = await photo.read()
        if not image_data:
            logger.error(f"❌ Файл пустой для трека {track_id}")
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "Файл пустой"}
            )

        logger.info(f"✅ Получено {len(image_data)} байт для артиста '{artist_name}'")

        # Создаем папку для изображений
        images_dir = os.path.join(BASE_DIR, "images")
        os.makedirs(images_dir, exist_ok=True)

        # Получаем ВСЕ треки этого артиста
        all_tracks = media_library.get_tracks()
        
        def normalize_artist_name(name):
            """Нормализация имени артиста для сравнения"""
            if not name:
                return ""
            # Приводим к нижнему регистру, убираем пробелы и спецсимволы
            import re
            name = str(name).lower().strip()
            name = re.sub(r'[^a-zа-яё0-9]', '', name)
            # Для русского языка: ё -> е
            name = name.replace('ё', 'е')
            return name

        target_artist_normalized = normalize_artist_name(artist_name)
        logger.info(f"🔍 Ищем треки артиста: '{artist_name}' -> '{target_artist_normalized}'")

        # Находим все треки этого артиста
        artist_tracks = []
        for t in all_tracks:
            track_artist = t.get('artist', '').strip()
            if normalize_artist_name(track_artist) == target_artist_normalized:
                artist_tracks.append(t)
                logger.debug(f"✅ Найден трек артиста: ID={t['id']}, '{track_artist}'")

        if not artist_tracks:
            artist_tracks = [track]  # если только этот трек

        logger.info(f"🎵 Найдено {len(artist_tracks)} треков артиста '{artist_name}'")

        # Сохраняем одно и то же фото для КАЖДОГО трека артиста
        updated_tracks = []
        errors = []

        for artist_track in artist_tracks:
            try:
                current_track_id = artist_track['id']
                current_artist_name = artist_track.get('artist', artist_name).strip()

                # Определяем расширение файла
                file_extension = Path(photo.filename).suffix.lower()
                if not file_extension:
                    file_extension = '.png'  # по умолчанию PNG

                # Создаем имя файла: {track_id}_artist.{extension}
                image_filename = f"{current_track_id}_artist{file_extension}"
                image_path = os.path.join(images_dir, image_filename)

                # Сохраняем файл (один и тот же для всех треков артиста)
                with open(image_path, "wb") as f:
                    f.write(image_data)

                # Проверяем что файл сохранился
                if not os.path.exists(image_path):
                    errors.append(f"Трек {current_track_id}: файл не сохранился")
                    continue

                file_size = os.path.getsize(image_path)
                logger.debug(f"💾 Файл сохранен: {image_filename} ({file_size} байт)")

                # Обновляем трек в медиатеке
                update_data = {
                    'image_path': image_path,
                    'artist': current_artist_name  # сохраняем имя артиста
                }

                # Используем метод update_track из media_library
                if hasattr(media_library, 'update_track'):
                    success = media_library.update_track(current_track_id, update_data)
                else:
                    # Fallback для других реализаций
                    for t in all_tracks:
                        if t['id'] == current_track_id:
                            t.update(update_data)
                            success = True
                            break
                    success = True

                if success:
                    updated_tracks.append({
                        'id': current_track_id,
                        'artist': current_artist_name,
                        'image_path': image_path,
                        'file_size': file_size
                    })
                    logger.info(f"✅ Фото сохранено для трека {current_track_id} ({current_artist_name})")
                else:
                    errors.append(f"Трек {current_track_id}: ошибка обновления в медиатеке")

            except Exception as e:
                error_msg = f"Трек {artist_track.get('id', 'unknown')}: {str(e)}"
                errors.append(error_msg)
                logger.error(f"❌ {error_msg}")

        # Возвращаем результат
        success_count = len(updated_tracks)

        if success_count > 0:
            logger.info(f"🎉 Фото успешно применено к {success_count} трекам артиста '{artist_name}'")
            
            # Обновляем кеш изображений для всех обновленных треков
            try:
                if hasattr(image_searcher, 'artist_cache'):
                    for updated_track in updated_tracks:
                        cache_key = f"{artist_name.lower()}_{updated_track['id']}"
                        image_searcher.artist_cache[cache_key] = updated_track['image_path']
                    logger.debug(f"✅ Обновлен кеш для {len(updated_tracks)} треков")
            except Exception as e:
                logger.warning(f"⚠️ Ошибка обновления кеша: {e}")

            return {
                "success": True,
                "message": f"Фото сохранено для {success_count} треков артиста '{artist_name}'",
                "artist": artist_name,
                "updated_tracks_count": success_count,
                "updated_tracks": [t['id'] for t in updated_tracks],
                "total_artist_tracks": len(artist_tracks),
                "errors": errors if errors else None,
                "image_path": updated_tracks[0]['image_path'] if updated_tracks else None
            }
        else:
            logger.error(f"❌ Не удалось сохранить фото ни для одного трека артиста '{artist_name}'")
            return JSONResponse(
                status_code=500,
                content={
                    "success": False, 
                    "error": f"Не удалось сохранить фото для артиста '{artist_name}'",
                    "errors": errors
                }
            )

    except Exception as e:
        logger.error(f"❌ Критическая ошибка загрузки фото: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": f"Внутренняя ошибка: {str(e)}"}
        )

@app.post("/api/tracks/{track_id}/save-artist-photo")
async def save_artist_photo(track_id: int, request_data: dict):
    """Сохранить фото артиста из URL с обработкой ошибок"""
    try:
        track = media_library.get_track(track_id)
        if not track:
            return JSONResponse(
                status_code=404,
                content={"success": False, "error": "Трек не найден"}
            )
        
        photo_url = request_data.get('photo_url')
        artist_name = request_data.get('artist', track.get('artist', ''))
        
        if not photo_url:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "URL фото не указан"}
            )
        
        # Скачиваем и сохраняем фото с правильным именем
        images_dir = os.path.join(BASE_DIR, "images")
        os.makedirs(images_dir, exist_ok=True)
        
        # Используем стандартное имя: {track_id}_artist.png
        image_path = os.path.join(images_dir, f"{track_id}_artist.png")
        
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            async with session.get(photo_url) as response:
                if response.status != 200:
                    return JSONResponse(
                        status_code=400,
                        content={"success": False, "error": f"Не удалось скачать фото (статус: {response.status})"}
                    )
                
                with open(image_path, 'wb') as f:
                    async for chunk in response.content.iter_chunked(1024 * 1024):  # 1MB chunks
                        f.write(chunk)
        
        if os.path.exists(image_path):
            # Проверяем что файл не пустой
            if os.path.getsize(image_path) == 0:
                os.remove(image_path)
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "error": "Скачанный файл пустой"}
                )
                
            media_library.update_track(track_id, {'image_path': image_path, 'artist': artist_name})
            return {
                "success": True, 
                "message": "Фото артиста сохранено",
                "image_path": image_path, 
                "artist": artist_name
            }
        
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": "Не удалось сохранить фото"}
        )
        
    except asyncio.TimeoutError:
        logger.error(f"❌ Таймаут при скачивании фото для трека {track_id}")
        return JSONResponse(
            status_code=408,
            content={"success": False, "error": "Таймаут при скачивании фото"}
        )
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения фото: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": f"Ошибка сохранения фото: {str(e)}"}
        )

# Также добавим обработчик для массового получения фото
@app.post("/api/tracks/batch-artist-photos")
async def get_batch_artist_photos(request_data: dict):
    """Получить фото для нескольких треков одновременно с обработкой ошибок"""
    try:
        track_ids = request_data.get('track_ids', [])
        if not track_ids:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "Список ID треков пуст"}
            )
        
        results = {}
        
        for track_id in track_ids:
            try:
                track = media_library.get_track(track_id)
                if track and track.get('image_path') and os.path.exists(track.get('image_path')):
                    results[track_id] = {
                        "success": True,
                        "has_photo": True,
                        "image_url": f"/api/tracks/{track_id}/artist-photo"
                    }
                else:
                    results[track_id] = {
                        "success": True,
                        "has_photo": False,
                        "placeholder_url": f"/api/tracks/{track_id}/artist-photo"
                    }
            except Exception as e:
                logger.warning(f"⚠️ Ошибка получения фото для трека {track_id}: {e}")
                results[track_id] = {
                    "success": False,
                    "error": str(e),
                    "placeholder_url": f"/api/tracks/{track_id}/artist-photo"
                }
        
        return {
            "success": True, 
            "results": results,
            "total_processed": len(track_ids),
            "successful": len([r for r in results.values() if r.get('success')]),
            "failed": len([r for r in results.values() if not r.get('success')])
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка массового получения фото: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": f"Ошибка массового получения фото: {str(e)}"}
        )

@app.get("/api/tracks/{track_id}/photo-status")
async def get_artist_photo_status(track_id: int):
    """Получить статус фото артиста для трека"""
    try:
        track = media_library.get_track(track_id)
        if not track:
            return {
                "success": False,
                "error": "Трек не найден",
                "has_photo": False
            }
        
        image_path = track.get('image_path')
        has_photo = bool(image_path and os.path.exists(image_path))
        
        status_info = {
            "success": True,
            "track_id": track_id,
            "artist": track.get('artist', 'Неизвестный артист'),
            "has_photo": has_photo,
            "image_path": image_path if has_photo else None,
            "file_exists": os.path.exists(image_path) if image_path else False
        }
        
        if has_photo:
            try:
                file_size = os.path.getsize(image_path)
                status_info.update({
                    "file_size": file_size,
                    "file_size_mb": round(file_size / 1024 / 1024, 2)
                })
            except Exception as e:
                status_info["file_size_error"] = str(e)
        
        return status_info
        
    except Exception as e:
        logger.error(f"❌ Ошибка получения статуса фото для трека {track_id}: {e}")
        return {
            "success": False,
            "error": str(e),
            "track_id": track_id,
            "has_photo": False
        }
@app.post("/api/tracks/photo-hashes")
async def get_tracks_photo_hashes(request_data: dict):
    """Получить хэши фото для списка треков"""
    try:
        track_ids = request_data.get('track_ids', [])
        if not track_ids:
            return JSONResponse({
                "success": False,
                "error": "Список ID треков пуст"
            })
        
        hashes = {}
        
        for track_id in track_ids:
            track = media_library.get_track(track_id)
            if track and track.get('image_path'):
                image_path = track['image_path']
                
                if os.path.exists(image_path):
                    # Генерируем MD5 хэш файла
                    import hashlib
                    try:
                        with open(image_path, 'rb') as f:
                            file_hash = hashlib.md5()
                            # Читаем файл частями для больших файлов
                            for chunk in iter(lambda: f.read(4096), b""):
                                file_hash.update(chunk)
                            
                            hashes[str(track_id)] = {
                                "hash": file_hash.hexdigest(),
                                "exists": True,
                                "size": os.path.getsize(image_path)
                            }
                    except Exception as e:
                        hashes[str(track_id)] = {
                            "hash": "error",
                            "error": str(e)
                        }
                else:
                    hashes[str(track_id)] = {
                        "hash": "missing",
                        "exists": False
                    }
            else:
                hashes[str(track_id)] = {
                    "hash": "no_photo",
                    "exists": False
                }
        
        return {
            "success": True,
            "hashes": hashes,
            "checked": len(track_ids),
            "with_photos": len([h for h in hashes.values() if h.get('exists')]),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка получения хэшей фото: {e}")
        return JSONResponse({
            "success": False,
            "error": str(e)
        })
# =========================
# AUDIO EDITOR API ENDPOINTS
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

@app.get("/api/tracks/{track_id}/full-track")
async def get_full_track(track_id: int):
    """Возвращает полный аудиофайл для предзагрузки"""
    try:
        track = media_library.get_track(track_id)
        if not track:
            raise HTTPException(status_code=404, detail="Track not found")
        
        return FileResponse(
            track['file_path'],
            filename=f"{track['artist']}_{track['title']}.mp3",
            media_type='audio/mpeg'
        )
    except Exception as e:
        logger.error(f"Ошибка загрузки полного трека: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/tracks/{track_id}/segment")
async def update_track_segment(track_id: int, segment_data: dict):
    """Обновляет отрезок трека"""
    try:
        start_time = segment_data.get('start_time', 0)
        duration = segment_data.get('duration', 30)
        
        track = media_library.get_track(track_id)
        if not track:
            raise HTTPException(status_code=404, detail="Track not found")
        
        # Обновляем данные трека
        track['segment_start'] = start_time
        track['segment_duration'] = duration
        
        # Сохраняем изменения (зависит от вашей реализации media_library)
        success = media_library.update_track(track_id, {
            'segment_start': start_time,
            'segment_duration': duration
        })
        
        if success:
            return {"success": True, "message": "Segment updated"}
        else:
            raise HTTPException(status_code=500, detail="Failed to update segment")
            
    except Exception as e:
        logger.error(f"❌ Ошибка обновления отрезка: {e}")
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
# ARTIST PHOTO CHECK API - ТОЛЬКО ТОЧНЫЙ поиск
# =========================

@app.get("/api/local/check-artist-photo")
async def check_artist_photo(artist: str):
    """Проверить наличие фото артиста в локальной папке artists (ТОЧНЫЙ поиск с полной очисткой)"""
    try:
        artists_dir = os.path.join(BASE_DIR, "artists")
        
        if not os.path.exists(artists_dir):
            return {
                "has_photo": False, 
                "message": "Папка artists не существует",
                "artist": artist,
                "found_files": [],
                "exact_match": None,
                "match_type": "none"
            }
        
        def clean_name_for_search(name):
            """Очистка имени для поиска: удаляем ВСЕ специальные, невидимые и мусорные символы"""
            import re
            import unicodedata
            
            if not name:
                return ""
            
            # 1. Убираем невидимые символы и мусор из WhatsApp/macOS
            # Список невидимых и мусорных символов
            garbage_chars = [
                # Невидимые символы
                '\u200B', '\u200C', '\u200D', '\u2060', '\uFEFF', '\u00AD',
                '\u180E', '\u200E', '\u200F', '\u202A', '\u202B', '\u202C',
                '\u202D', '\u202E', '\u2066', '\u2067', '\u2068', '\u2069',
                
                # Эмодзи и пиктограммы (часто из WhatsApp)
                '\u263A-\u27BF',  # Разные символы
                '\U0001F300-\U0001F9FF',  # Эмодзи блок 1
                '\U0001FA00-\U0001FA6F',  # Эмодзи блок 2
                '\u2600-\u26FF',  # Разные символы
                '\u2700-\u27BF',  # Dingbats
                
                # Специальные цифры и символы (например, ⁠ - это U+2060)
                '\u2070', '\u00B9', '\u00B2', '\u00B3', '\u2074', '\u2075',
                '\u2076', '\u2077', '\u2078', '\u2079', '\u207A', '\u207B',
                '\u207C', '\u207D', '\u207E',
                
                # WhatsApp/Telegram форматирование
                '\u2022', '\u2023', '\u2043', '\u204C', '\u204D', '\u2219',
                '\u25E6', '\u25AA', '\u25AB', '\u25CF', '\u25CB', '\u25A0',
                
                # Разные дефисы и тире (из разных источников)
                '\u2010', '\u2011', '\u2012', '\u2013', '\u2014', '\u2015',
                '\u2E3A', '\u2E3B', '\uFE58', '\uFE63', '\uFF0D',
            ]
            
            # Заменяем все эти символы на пробелы
            for char_range in garbage_chars:
                if '-' in char_range and len(char_range) > 1:
                    # Это диапазон символов
                    start, end = ord(char_range[0]), ord(char_range[-1])
                    for codepoint in range(start, end + 1):
                        name = name.replace(chr(codepoint), ' ')
                else:
                    # Одиночный символ
                    name = name.replace(char_range, ' ')
            
            # 2. Нормализуем Unicode (преобразуем комбинированные символы в обычные)
            # Например, é → e
            name = unicodedata.normalize('NFKD', name)
            
            # 3. Убираем все акценты, диакритические знаки
            name = ''.join(c for c in name if not unicodedata.combining(c))
            
            # 4. Заменяем все нестандартные пробелы на обычные
            whitespace_chars = [
                '\u00A0', '\u1680', '\u2000', '\u2001', '\u2002', '\u2003',
                '\u2004', '\u2005', '\u2006', '\u2007', '\u2008', '\u2009',
                '\u200A', '\u202F', '\u205F', '\u3000', '\u180E',
            ]
            for ws in whitespace_chars:
                name = name.replace(ws, ' ')
            
            # 5. Приводим к нижнему регистру
            name = name.lower()
            
            # 6. Убираем точки в начале строки и другие начальные мусорные символы
            name = re.sub(r'^[\.\s\-_\*\#\+]+', '', name)
            
            # 7. Убираем ВСЕ оставшиеся специальные символы кроме букв, цифр и пробелов
            # Разрешаем: буквы (кириллица и латиница), цифры, пробелы
            name = re.sub(r'[^a-zа-яё0-9\s]', ' ', name)
            
            # 8. Заменяем множественные пробелы на один
            name = re.sub(r'\s+', ' ', name)
            
            # 9. Убираем пробелы в начале и конце
            name = name.strip()
            
            return name
        
        # Поддерживаемые расширения
        supported_extensions = ['.png', '.jpg', '.jpeg', '.webp']
        found_files = []
        exact_match_file = None
        
        # Очищаем имя артиста для поиска
        artist_clean = clean_name_for_search(artist)
        
        logger.info(f"🔍 Поиск фото для '{artist}' -> очищено: '{artist_clean}'")
        
        # Если после очистки пусто - возвращаем ошибку
        if not artist_clean:
            return {
                "has_photo": False,
                "artist": artist,
                "search_name": "",
                "found_files": [],
                "exact_match": None,
                "match_type": "empty",
                "message": "Имя артиста после очистки пустое"
            }
        
        # Поиск файлов
        for filename in os.listdir(artists_dir):
            file_lower = filename.lower()
            
            # Проверяем расширение
            if any(file_lower.endswith(ext) for ext in supported_extensions):
                # Получаем имя файла без расширения
                file_base = os.path.splitext(filename)[0]
                
                # Очищаем имя файла так же
                file_clean = clean_name_for_search(file_base)
                
                # Проверяем совпадение (после очистки)
                if artist_clean == file_clean:
                    exact_match_file = filename
                    found_files.append(filename)
                    break
        
        # Определяем результат
        has_photo = bool(exact_match_file)
        result_file = exact_match_file
        match_type = "exact" if exact_match_file else "none"
        
        logger.info(f"🔍 Результат для '{artist}': {match_type}, файл: {result_file}")
        
        return {
            "has_photo": has_photo,
            "artist": artist,
            "search_name": artist_clean,
            "found_files": found_files,
            "exact_match": result_file,
            "match_type": match_type,
            "message": f"Найдено точное совпадение: {result_file}" if result_file else "Фото не найдено"
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка проверки фото артиста {artist}: {e}")
        return {
            "has_photo": False,
            "error": str(e),
            "artist": artist,
            "found_files": [],
            "match_type": "error"
        }
# =========================
# PRESENTATION GENERATION API
# =========================

@app.post("/api/generate/presentation")
async def generate_presentation(request_data: dict):
    """Генерация презентации с поддержкой кастомной длительности отрезка"""
    try:
        logger.info("🎬 Запуск генерации презентации...")
        
        # Проверяем наличие base.pptx
        base_path = os.path.join(BASE_DIR, "base.pptx")
        if not os.path.exists(base_path):
            logger.info("📦 base.pptx не найден, скачиваем из Dropbox...")
            if not dropbox_storage.download_base_pptx(base_path):
                raise HTTPException(status_code=500, detail="Не удалось скачать base.pptx из облака")
        
        # Проверяем наличие треков
        tracks_from_request = request_data.get("tracks")
        if tracks_from_request:
            logger.info(f"✅ Используем {len(tracks_from_request)} треков из запроса")
            tracks = tracks_from_request
        else:
            tracks = media_library.get_tracks()
            if len(tracks) < 1:
                raise HTTPException(status_code=400, detail="Недостаточно треков для генерации")

        logger.info(f"📊 Генерация с {len(tracks)} треками")
        
        title = request_data.get("title", "Музыкальное Лото")
        make_bw = request_data.get("design", {}).get("make_bw", False)
        
        # Получаем кастомную длительность из запроса
        segment_duration = request_data.get("segment_duration")
        if segment_duration:
            # Проверяем что длительность в допустимых пределах
            if not (5 <= segment_duration <= 120):
                raise HTTPException(
                    status_code=400, 
                    detail="Длительность отрезка должна быть от 5 до 120 секунд"
                )
            logger.info(f"🎵 Используется кастомная длительность отрезка: {segment_duration} сек")
        
        logger.info(f"📊 Параметры генерации: '{title}', ЧБ: {make_bw}, треков: {len(tracks)}")
        
        generator = ModernPresentationGenerator(base_path)
        
        # Передаем кастомную длительность в генератор
        result_path = generator.generate(
            game_title=title,
            tracks=tracks,
            make_bw=make_bw,
            use_parallel=True,
            segment_duration=segment_duration  # передаем кастомную длительность
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
# IMPORT/EXPORT SYSTEM (LOW RAM USAGE)
# =========================

import zipfile
import shutil

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

# =========================
# IMAGE PROCESSING API (ENDPOINTS ONLY)
# =========================

from image_processor import image_processor
import base64
from io import BytesIO
from PIL import Image
import os
import logging
import shutil
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

def get_backup_image_path(original_path):
    """Получить путь к backup копии изображения"""
    backup_dir = os.path.join(BASE_DIR, "images", "backup")
    os.makedirs(backup_dir, exist_ok=True)
    
    filename = os.path.basename(original_path)
    return os.path.join(backup_dir, f"original_{filename}")

def create_image_backup(original_path):
    """Создать backup копию оригинального изображения"""
    try:
        if not os.path.exists(original_path):
            return False
            
        backup_path = get_backup_image_path(original_path)
        
        # Создаем backup только если его еще нет
        if not os.path.exists(backup_path):
            shutil.copy2(original_path, backup_path)
            logger.info(f"✅ Backup создан: {backup_path}")
        else:
            logger.info(f"ℹ️ Backup уже существует: {backup_path}")
            
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка создания backup: {e}")
        return False

def restore_image_from_backup(original_path):
    """Восстановить изображение из backup"""
    try:
        backup_path = get_backup_image_path(original_path)
        
        if not os.path.exists(backup_path):
            logger.error(f"❌ Backup не найден: {backup_path}")
            return False
            
        # Восстанавливаем из backup
        shutil.copy2(backup_path, original_path)
        logger.info(f"✅ Изображение восстановлено из backup: {original_path}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка восстановления из backup: {e}")
        return False

@app.post("/api/tracks/{track_id}/process-image")
async def process_track_image(track_id: int, request_data: dict):
    try:
        operations = request_data.get('operations', [])
        container_size = request_data.get('container_size', {})
        image_transform = request_data.get('image_transform', {})
        logger.info(f"🎨 Processing image for track {track_id}, operations: {len(operations)}")
        
        track = media_library.get_track(track_id)
        if not track or not track.get('image_path'):
            return JSONResponse({"success": False, "error": "Трек или фото не найдено"})
        
        original_image_path = track['image_path']
        if not os.path.exists(original_image_path):
            return JSONResponse({"success": False, "error": "Файл фото не найдено"})
        
        # Создаем backup перед первой операцией редактирования
        if operations:
            create_image_backup(original_image_path)
        
        with open(original_image_path, "rb") as f:
            original_image_data = base64.b64encode(f.read()).decode()
        image_base64 = f"data:image/png;base64,{original_image_data}"
        current_img = image_base64

        for op in operations:
            logger.info(f"🔄 Applying operation: {op['type']}")
            
            if op['type'] == 'erase':
                current_img = image_processor.apply_eraser_batch(
                    current_img, op['data']['operations'], container_size, image_transform
                )
            elif op['type'] == 'crop':
                current_img = image_processor.apply_crop(
                    current_img, op['data']['rect'], container_size, image_transform
                )
            elif op['type'] == 'selection':
                current_img = image_processor.apply_selection_mask(
                    current_img, op['data']['points'], container_size, image_transform
                )
            else:
                logger.warning(f"⚠️ Unknown operation type: {op['type']}")
                continue

            if current_img is None:
                return JSONResponse({"success": False, "error": f"Ошибка при операции {op['type']}"})

        # Подготавливаем результат для сохранения
        if isinstance(current_img, Image.Image):
            # Если это PIL Image, конвертируем в base64
            image_data = image_processor.image_to_base64(current_img)
            result_image = current_img
        elif isinstance(current_img, str) and current_img.startswith('data:'):
            # Если это base64 строка, извлекаем данные
            image_data = current_img.split(',')[1]
            result_pil = Image.open(BytesIO(base64.b64decode(image_data)))
            result_image = result_pil
        else:
            logger.error("❌ Invalid image format after processing")
            return JSONResponse({"success": False, "error": "Неверный формат изображения после обработки"})

        # Сохраняем результат
        if image_processor.save_image(result_image, original_image_path):
            logger.info(f"✅ Image successfully processed and saved: {original_image_path}")
            return JSONResponse({
                "success": True,
                "image": f"data:image/png;base64,{image_data}",
                "image_path": original_image_path
            })
        else:
            logger.error("❌ Failed to save image")
            return JSONResponse({"success": False, "error": "Ошибка сохранения"})

    except Exception as e:
        logger.error(f"❌ Ошибка обработки изображения: {e}", exc_info=True)
        return JSONResponse({"success": False, "error": str(e)})

@app.post("/api/tracks/{track_id}/preview-eraser")
async def preview_eraser(track_id: int, request_data: dict):
    try:
        image_data = request_data.get('image')
        erase_operations = request_data.get('operations', [])
        container_size = request_data.get('container_size', {})
        image_transform = request_data.get('image_transform', {})
        if not image_data:
            return JSONResponse({"success": False, "error": "Изображение не предоставлено"})
        result = image_processor.apply_eraser_batch(image_data, erase_operations, container_size, image_transform)
        if result:
            b64 = image_processor.image_to_base64(result)
            return JSONResponse({"success": True, "image": f"data:image/png;base64,{b64}"})
        else:
            return JSONResponse({"success": False, "error": "Ошибка предпросмотра"})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/tracks/{track_id}/original-image")
async def get_original_image(track_id: int):
    track = media_library.get_track(track_id)
    if not track or not track.get('image_path'):
        return JSONResponse({"success": False, "error": "Трек не найден"})
    path = track['image_path']
    if not os.path.exists(path):
        return JSONResponse({"success": False, "error": "Фото не найдено"})
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
        return JSONResponse({
            "success": True,
            "image": f"data:image/png;base64,{b64}",
            "image_path": path
        })

@app.post("/api/tracks/{track_id}/reset-image")
async def reset_track_image(track_id: int):
    """Сброс изображения трека к оригиналу"""
    try:
        logger.info(f"🔄 Resetting image for track {track_id}")
        
        track = media_library.get_track(track_id)
        if not track:
            logger.error(f"❌ Track {track_id} not found")
            return JSONResponse({"success": False, "error": "Трек не найден"})
        
        image_path = track.get('image_path')
        if not image_path or not os.path.exists(image_path):
            logger.error(f"❌ Image file not found: {image_path}")
            return JSONResponse({"success": False, "error": "Файл изображения не найден"})
        
        # Пытаемся восстановить из backup
        if restore_image_from_backup(image_path):
            logger.info(f"✅ Image restored from backup for track {track_id}")
            return JSONResponse({
                "success": True, 
                "message": "Изображение восстановлено из резервной копии"
            })
        
        # Если backup нет, пробуем перезагрузить оригинал из интернета
        artist = track.get('artist', '')
        if artist:
            logger.info(f"🔄 Trying to reload original image for artist: {artist}")
            
            # Пытаемся найти новое фото артиста
            new_photo_path = image_searcher.fetch_artist_png(artist, track_id)
            if new_photo_path and os.path.exists(new_photo_path):
                # Копируем новое фото на место старого
                shutil.copy2(new_photo_path, image_path)
                logger.info(f"✅ Image reloaded from internet for track {track_id}")
                return JSONResponse({
                    "success": True, 
                    "message": "Изображение перезагружено из интернета"
                })
        
        # Если ничего не помогло, возвращаем ошибку
        logger.error(f"❌ Cannot reset image for track {track_id}")
        return JSONResponse({
            "success": False, 
            "error": "Не удалось восстановить оригинальное изображение"
        })
        
    except Exception as e:
        logger.error(f"❌ Ошибка сброса изображения: {e}")
        return JSONResponse({"success": False, "error": str(e)})

@app.post("/api/tracks/{track_id}/create-image-backup")
async def create_track_image_backup(track_id: int):
    """Создать backup изображения трека"""
    try:
        logger.info(f"💾 Creating image backup for track {track_id}")
        
        track = media_library.get_track(track_id)
        if not track:
            logger.error(f"❌ Track {track_id} not found")
            return JSONResponse({"success": False, "error": "Трек не найден"})
        
        image_path = track.get('image_path')
        if not image_path or not os.path.exists(image_path):
            logger.error(f"❌ Image file not found: {image_path}")
            return JSONResponse({"success": False, "error": "Файл изображения не найден"})
        
        if create_image_backup(image_path):
            return JSONResponse({
                "success": True, 
                "message": "Резервная копия изображения создана"
            })
        else:
            return JSONResponse({
                "success": False, 
                "error": "Не удалось создать резервную копию"
            })
            
    except Exception as e:
        logger.error(f"❌ Ошибка создания backup: {e}")
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/tracks/{track_id}/image-backup-status")
async def get_image_backup_status(track_id: int):
    """Получить статус backup изображения трека"""
    try:
        track = media_library.get_track(track_id)
        if not track:
            return JSONResponse({"success": False, "error": "Трек не найден"})
        
        image_path = track.get('image_path')
        if not image_path:
            return JSONResponse({"success": False, "error": "Изображение не найдено"})
        
        backup_path = get_backup_image_path(image_path)
        has_backup = os.path.exists(backup_path)
        
        backup_info = {}
        if has_backup:
            backup_size = os.path.getsize(backup_path)
            backup_info = {
                "exists": True,
                "size": backup_size,
                "size_mb": round(backup_size / 1024 / 1024, 2),
                "path": backup_path,
                "created_time": datetime.fromtimestamp(os.path.getctime(backup_path)).isoformat()
            }
        else:
            backup_info = {
                "exists": False,
                "message": "Резервная копия не найдена"
            }
        
        return JSONResponse({
            "success": True,
            "track_id": track_id,
            "has_backup": has_backup,
            "backup_info": backup_info,
            "original_image": {
                "exists": os.path.exists(image_path),
                "path": image_path
            }
        })
        
    except Exception as e:
        logger.error(f"❌ Ошибка получения статуса backup: {e}")
        return JSONResponse({"success": False, "error": str(e)})

@app.post("/api/tracks/batch-create-backups")
async def batch_create_image_backups():
    """Создать backup для всех изображений треков"""
    try:
        logger.info("💾 Creating backups for all track images")
        
        tracks = media_library.get_tracks()
        successful = 0
        failed = 0
        results = []
        
        for track in tracks:
            track_id = track.get('id')
            image_path = track.get('image_path')
            
            if image_path and os.path.exists(image_path):
                if create_image_backup(image_path):
                    successful += 1
                    results.append({
                        "track_id": track_id,
                        "artist": track.get('artist', ''),
                        "status": "success",
                        "message": "Backup created"
                    })
                else:
                    failed += 1
                    results.append({
                        "track_id": track_id,
                        "artist": track.get('artist', ''),
                        "status": "failed",
                        "message": "Failed to create backup"
                    })
            else:
                failed += 1
                results.append({
                    "track_id": track_id,
                    "artist": track.get('artist', ''),
                    "status": "skipped",
                    "message": "No image found"
                })
        
        logger.info(f"✅ Batch backup completed: {successful} successful, {failed} failed")
        
        return JSONResponse({
            "success": True,
            "message": f"Создано резервных копий: {successful} успешно, {failed} ошибок",
            "results": results,
            "statistics": {
                "total_tracks": len(tracks),
                "successful_backups": successful,
                "failed_backups": failed
            }
        })
        
    except Exception as e:
        logger.error(f"❌ Ошибка пакетного создания backup: {e}")
        return JSONResponse({"success": False, "error": str(e)})

@app.post("/api/tracks/batch-reset-images")
async def batch_reset_track_images(request_data: dict = None):
    """Сбросить изображения для нескольких треков"""
    try:
        track_ids = request_data.get('track_ids', []) if request_data else []
        
        if not track_ids:
            # Если не указаны конкретные треки, сбрасываем все
            tracks = media_library.get_tracks()
            track_ids = [track['id'] for track in tracks]
        
        logger.info(f"🔄 Batch resetting images for {len(track_ids)} tracks")
        
        results = []
        successful = 0
        failed = 0
        
        for track_id in track_ids:
            try:
                # Используем существующий эндпоинт для каждого трека
                track = media_library.get_track(track_id)
                if not track:
                    results.append({
                        "track_id": track_id,
                        "status": "failed",
                        "message": "Трек не найден"
                    })
                    failed += 1
                    continue
                
                image_path = track.get('image_path')
                if not image_path or not os.path.exists(image_path):
                    results.append({
                        "track_id": track_id,
                        "artist": track.get('artist', ''),
                        "status": "skipped",
                        "message": "Изображение не найдено"
                    })
                    continue
                
                # Восстанавливаем из backup
                if restore_image_from_backup(image_path):
                    results.append({
                        "track_id": track_id,
                        "artist": track.get('artist', ''),
                        "status": "success",
                        "message": "Изображение восстановлено"
                    })
                    successful += 1
                else:
                    results.append({
                        "track_id": track_id,
                        "artist": track.get('artist', ''),
                        "status": "failed",
                        "message": "Не удалось восстановить"
                    })
                    failed += 1
                    
            except Exception as e:
                logger.error(f"❌ Ошибка сброса трека {track_id}: {e}")
                results.append({
                    "track_id": track_id,
                    "status": "failed",
                    "message": str(e)
                })
                failed += 1
        
        logger.info(f"✅ Batch reset completed: {successful} successful, {failed} failed")
        
        return JSONResponse({
            "success": True,
            "message": f"Сброшено изображений: {successful} успешно, {failed} ошибок",
            "results": results,
            "statistics": {
                "total_processed": len(track_ids),
                "successful": successful,
                "failed": failed
            }
        })
        
    except Exception as e:
        logger.error(f"❌ Ошибка пакетного сброса изображений: {e}")
        return JSONResponse({"success": False, "error": str(e)})

@app.delete("/api/tracks/{track_id}/delete-image-backup")
async def delete_track_image_backup(track_id: int):
    """Удалить backup изображения трека"""
    try:
        track = media_library.get_track(track_id)
        if not track:
            return JSONResponse({"success": False, "error": "Трек не найден"})
        
        image_path = track.get('image_path')
        if not image_path:
            return JSONResponse({"success": False, "error": "Изображение не найдено"})
        
        backup_path = get_backup_image_path(image_path)
        
        if not os.path.exists(backup_path):
            return JSONResponse({"success": False, "error": "Резервная копия не найдена"})
        
        os.remove(backup_path)
        logger.info(f"🗑️ Backup deleted for track {track_id}: {backup_path}")
        
        return JSONResponse({
            "success": True,
            "message": "Резервная копия изображения удалена"
        })
        
    except Exception as e:
        logger.error(f"❌ Ошибка удаления backup: {e}")
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/tracks/image-backups/overview")
async def get_all_image_backups_overview():
    """Получить обзор всех backup изображений"""
    try:
        backup_dir = os.path.join(BASE_DIR, "images", "backup")
        
        if not os.path.exists(backup_dir):
            return JSONResponse({
                "success": True,
                "backups": [],
                "statistics": {
                    "total_backups": 0,
                    "total_size_mb": 0
                }
            })
        
        backups = []
        total_size = 0
        
        for filename in os.listdir(backup_dir):
            if filename.startswith('original_'):
                file_path = os.path.join(backup_dir, filename)
                file_size = os.path.getsize(file_path)
                total_size += file_size
                
                # Извлекаем track_id из имени файла
                try:
                    # Формат: original_{track_id}_artist.png
                    parts = filename.split('_')
                    if len(parts) >= 2:
                        track_id = int(parts[1])
                        track = media_library.get_track(track_id)
                        artist = track.get('artist', 'Unknown') if track else 'Unknown'
                    else:
                        track_id = None
                        artist = 'Unknown'
                except:
                    track_id = None
                    artist = 'Unknown'
                
                backups.append({
                    "filename": filename,
                    "track_id": track_id,
                    "artist": artist,
                    "size": file_size,
                    "size_mb": round(file_size / 1024 / 1024, 2),
                    "created_time": datetime.fromtimestamp(os.path.getctime(file_path)).isoformat()
                })
        
        return JSONResponse({
            "success": True,
            "backups": sorted(backups, key=lambda x: x['track_id'] or 0),
            "statistics": {
                "total_backups": len(backups),
                "total_size_mb": round(total_size / 1024 / 1024, 2)
            }
        })
        
    except Exception as e:
        logger.error(f"❌ Ошибка получения обзора backup: {e}")
        return JSONResponse({"success": False, "error": str(e)})
if __name__ == "__main__":
    import uvicorn
    logger.info("🎵 Music Loto Maker Server v3.0 Starting...")
    logger.info(f"🔧 Metadata processor: {type(metadata_processor).__name__}")
    logger.info("🎯 Key features: Smart segments, File management, Presentation generation, Duplicate checking")
    logger.info("🌐 Music download: Yandex Music only")
    logger.info(f"🌐 Server running on http://0.0.0.0:{PORT}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)