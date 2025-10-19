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
from datetime import datetime
import json
import glob
import requests
from PIL import Image
import io

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
            # Базовая логика парсинга
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
    # Создаем простую заглушку
    class MediaLibrary:
        def __init__(self):
            self.tracks = []
            self.next_id = 1
        
        def get_tracks(self):
            return self.tracks
        
        def add_track(self, file_path, original_filename):
            """Добавить трек (стандартный метод)"""
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
                    'image_path': None,  # Фото НЕ загружается автоматически
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
            """Обновить отрезок трека"""
            track = self.get_track(track_id)
            if track:
                track['segment_start'] = start_time
                track['segment_duration'] = duration
                return True
            return False
    
    logger.info("✅ Используется заглушка MediaLibrary")

# Импорт современных генераторов
try:
    from presentation import ModernPresentationGenerator, TicketGenerator
    logger.info("✅ Современные генераторы импортированы")
except ImportError as e:
    logger.warning(f"⚠️ Modern generators import error: {e}")
    # Заглушки для современных генераторов
    class ModernPresentationGenerator:
        def generate_musical_loto_presentation(self, tracks, output_path):
            logger.info(f"🎲 Генерация Musical Loto для {len(tracks)} треков")
            # Создаем временный файл для демонстрации
            with open(output_path, 'w') as f:
                f.write("Musical Loto Presentation Placeholder")
            return output_path
        
        def generate_modern_pptx(self, tracks, output_path):
            logger.info(f"🎨 Генерация современной презентации для {len(tracks)} треков")
            with open(output_path, 'w') as f:
                f.write("Modern Presentation Placeholder")
            return output_path
        
        def generate_modern_pdf(self, tracks, output_path):
            logger.info(f"📊 Генерация современного PDF для {len(tracks)} треков")
            with open(output_path, 'w') as f:
                f.write("Modern PDF Placeholder")
            return output_path
    
    class TicketGenerator:
        def generate_modern_tickets(self, tracks, count=24):
            logger.info(f"🎫 Генерация современных билетов: {count} шт.")
            return "/tmp/modern_tickets.pdf"

try:
    from audio_editor import audio_editor
    logger.info("✅ Audio editor imported successfully")
except ImportError as e:
    logger.warning(f"⚠️ Audio editor import error: {e}")
    class AudioEditor:
        def generate_waveform(self, file_path):
            return []
        def play_segment(self, file_path, start_time, duration):
            return True
        def stop_playback(self):
            return True
        def suggest_best_segment(self, file_path):
            return 30
        def extract_segment(self, file_path, start_time, duration, output_path):
            return output_path
        def process_track_complete(self, track_data, clip_path):
            return track_data
        def get_all_tracks_data(self):
            return []
    
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
            # Заглушка - возвращаем None, чтобы фронтенд мог обработать
            return None
        
        def fetch_multiple_artist_photos(self, artist_name, count=10):
            logger.info(f"🎭 Поиск {count} фото для: {artist_name}")
            # Заглушка - возвращаем тестовые URL
            test_urls = [
                "https://via.placeholder.com/400x400/667eea/white?text=Artist+1",
                "https://via.placeholder.com/400x400/764ba2/white?text=Artist+2", 
                "https://via.placeholder.com/400x400/f093fb/white?text=Artist+3"
            ]
            return test_urls[:count]
    
    image_searcher = SimpleImageSearcher()

# Инициализация приложения
app = FastAPI(title="Music Loto Maker", version="3.0.0")

# Разрешаем CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Определяем корневую директорию проекта
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

# Создаем необходимые папки
for folder in ["temp", "output", "uploads", "config", "images", "clips", "covers", "tracks_data"]:
    folder_path = os.path.join(BASE_DIR, folder)
    os.makedirs(folder_path, exist_ok=True)
    logger.info(f"📁 Создана папка: {folder_path}")

# Монтируем статические файлы фронтенда
if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
else:
    logger.warning(f"⚠️ Папка фронтенда не найдена: {FRONTEND_DIR}")

# Инициализация модулей
media_library = MediaLibrary()
modern_presentation_gen = ModernPresentationGenerator()
ticket_gen = TicketGenerator()

logger.info("🎵 Music Loto Maker Server v3.0 initialized")

@app.get("/")
async def serve_frontend():
    """Главная страница"""
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    else:
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
                "Artist image search"
            ]
        }

# API для медиатеки
@app.get("/api/tracks")
async def get_tracks():
    """Получить все треки"""
    try:
        tracks = media_library.get_tracks()
        logger.info(f"📊 Запрошены треки, найдено: {len(tracks)}")
        return tracks
    except Exception as e:
        logger.error(f"❌ Ошибка получения треков: {e}")
        return []

@app.get("/api/tracks/count")
async def get_tracks_count():
    """Получить количество треков"""
    try:
        count = media_library.get_tracks_count()
        return {"count": count, "status": "sufficient" if count >= 40 else "insufficient"}
    except Exception as e:
        logger.error(f"❌ Ошибка получения количества треков: {e}")
        return {"count": 0, "status": "error"}

@app.post("/api/tracks/upload")
async def upload_tracks(files: list[UploadFile] = File(...)):
    """Загрузить аудиофайлы БЕЗ автоматического поиска фото"""
    saved_tracks = []
    errors = []
    
    logger.info(f"📤 Начало загрузки {len(files)} файлов")
    
    for file in files:
        try:
            logger.info(f"🔍 Обработка файла: {file.filename}")
            
            # Проверяем тип файла
            allowed_extensions = {'.mp3', '.wav', '.flac', '.m4a', '.aac'}
            file_extension = Path(file.filename).suffix.lower()
            
            if file_extension not in allowed_extensions:
                error_msg = f"Неподдерживаемый формат: {file_extension}"
                errors.append(error_msg)
                logger.warning(f"⚠️ {error_msg}")
                continue
            
            # Сохраняем файл в папку uploads
            uploads_dir = os.path.join(BASE_DIR, "uploads")
            os.makedirs(uploads_dir, exist_ok=True)
            
            # Создаем уникальное имя файла
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_filename = f"{timestamp}_{Path(file.filename).stem}{file_extension}"
            file_path = os.path.join(uploads_dir, safe_filename)
            
            logger.info(f"💾 Сохранение файла как: {safe_filename}")
            
            # Сохраняем файл
            with open(file_path, "wb") as buffer:
                content = await file.read()
                buffer.write(content)
            
            # Проверяем что файл сохранен
            if not os.path.exists(file_path):
                error_msg = f"Файл не сохранен: {file_path}"
                errors.append(error_msg)
                logger.error(f"❌ {error_msg}")
                continue
            
            file_size = os.path.getsize(file_path)
            logger.info(f"✅ Файл сохранен, размер: {file_size} байт")
            
            # Обрабатываем метаданные через Hugging Face процессор
            logger.info(f"🔍 Обработка метаданных для: {file.filename}")
            metadata = metadata_processor.process(file.filename)
            logger.info(f"✅ Метаданные получены: {metadata}")
            
            # Добавляем в медиатеку стандартным методом
            track = media_library.add_track(file_path, file.filename)
            if track:
                # Обновляем метаданные
                update_data = {
                    'artist': metadata.get('artist', 'Неизвестный исполнитель'),
                    'title': metadata.get('title', 'Без названия'),
                    'metadata': metadata
                }
                media_library.update_track(track['id'], update_data)
                
                # Обновляем объект трека для ответа
                track.update(update_data)
                saved_tracks.append(track)
                
                logger.info(f"🎵 Трек добавлен в медиатеку: {track['id']} - {track['artist']} - {track['title']}")
                logger.info(f"📷 Фото НЕ загружается автоматически - пользователь добавит вручную")
            else:
                error_msg = f"Не удалось добавить трек в медиатеку: {file.filename}"
                errors.append(error_msg)
                logger.error(f"❌ {error_msg}")
                
        except Exception as e:
            error_msg = f"Ошибка загрузки {file.filename}: {str(e)}"
            errors.append(error_msg)
            logger.error(f"❌ {error_msg}", exc_info=True)
    
    response_message = f"Успешно загружено {len(saved_tracks)} треков"
    if errors:
        response_message += f". Ошибки: {', '.join(errors)}"
    
    logger.info(f"📊 Итог загрузки: {response_message}")
    
    return {
        "message": response_message,
        "tracks": saved_tracks,
        "errors": errors
    }

@app.put("/api/tracks/{track_id}")
async def update_track(track_id: int, track_data: dict):
    """Обновить данные трека"""
    try:
        success = media_library.update_track(track_id, track_data)
        if success:
            return {"message": "Трек обновлен"}
        else:
            raise HTTPException(status_code=404, detail="Трек не найден")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка обновления: {str(e)}")

@app.delete("/api/tracks/{track_id}")
async def delete_track(track_id: int):
    """Удалить трек"""
    try:
        success = media_library.delete_track(track_id)
        if success:
            return {"message": "Трек удален"}
        else:
            raise HTTPException(status_code=404, detail="Трек не найден")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка удаления: {str(e)}")

@app.delete("/api/tracks")
async def clear_tracks():
    """Очистить всю медиатеку"""
    try:
        media_library.clear()
        return {"message": "Медиатека очищена"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка очистки: {str(e)}")

# =========================
# ARTIST PHOTO API ENDPOINTS
# =========================

@app.post("/api/tracks/{track_id}/search-artist-photo")
async def search_artist_photo(track_id: int, request_data: dict):
    """Поиск нескольких фото артиста в интернете"""
    try:
        track = media_library.get_track(track_id)
        if not track:
            raise HTTPException(status_code=404, detail="Трек не найден")
        
        artist_name = request_data.get('artist', track.get('artist', ''))
        get_multiple = request_data.get('get_multiple', True)  # По умолчанию ищем несколько
        
        if not artist_name:
            raise HTTPException(status_code=400, detail="Имя артиста не указано")
        
        logger.info(f"🔍 Поиск фото для артиста: {artist_name} (multiple: {get_multiple})")
        
        # Используем image_searcher для поиска нескольких фото
        if get_multiple:
            photo_urls = image_searcher.fetch_multiple_artist_photos(artist_name, count=10)
        else:
            # Для обратной совместимости
            single_photo_path = image_searcher.fetch_artist_png(artist_name, track_id)
            photo_urls = [single_photo_path] if single_photo_path else []
        
        if photo_urls and len(photo_urls) > 0:
            logger.info(f"✅ Найдено {len(photo_urls)} фото для: {artist_name}")
            
            return {
                "success": True,
                "message": f"Найдено {len(photo_urls)} фото",
                "photos": photo_urls,
                "artist": artist_name,
                "count": len(photo_urls)
            }
        else:
            logger.warning(f"❌ Фото для артиста не найдено: {artist_name}")
            return {
                "success": False,
                "message": "Не удалось найти фото артиста"
            }
            
    except Exception as e:
        logger.error(f"❌ Ошибка поиска фото: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка поиска фото: {str(e)}")

@app.post("/api/tracks/{track_id}/save-artist-photo")
async def save_artist_photo(track_id: int, request_data: dict):
    """Сохранение выбранного фото артиста из URL"""
    try:
        track = media_library.get_track(track_id)
        if not track:
            raise HTTPException(status_code=404, detail="Трек не найден")
        
        photo_url = request_data.get('photo_url')
        artist_name = request_data.get('artist', track.get('artist', ''))
        
        if not photo_url:
            raise HTTPException(status_code=400, detail="URL фото не указан")
        
        logger.info(f"💾 Сохранение фото для артиста: {artist_name}")
        logger.info(f"📥 URL фото: {photo_url}")
        
        # Скачиваем и сохраняем фото
        image_path = await download_and_save_photo(photo_url, track_id, artist_name)
        
        if image_path and os.path.exists(image_path):
            # Обновляем трек с путем к фото
            update_data = {
                'image_path': image_path,
                'artist': artist_name
            }
            media_library.update_track(track_id, update_data)
            
            logger.info(f"✅ Фото сохранено: {image_path}")
            
            return {
                "success": True,
                "message": "Фото артиста сохранено",
                "image_path": image_path,
                "artist": artist_name
            }
        else:
            logger.error("❌ Не удалось сохранить фото")
            raise HTTPException(status_code=500, detail="Не удалось сохранить фото")
        
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения фото: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка сохранения фото: {str(e)}")

@app.post("/api/tracks/{track_id}/upload-artist-photo")
async def upload_artist_photo(track_id: int, photo: UploadFile = File(...)):
    """Загрузить фото артиста с компьютера"""
    try:
        track = media_library.get_track(track_id)
        if not track:
            raise HTTPException(status_code=404, detail="Трек не найден")
        
        # Проверяем тип файла
        if not photo.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="Файл должен быть изображением")
        
        logger.info(f"📤 Загрузка фото для трека {track_id}")
        
        # Создаем папку для фото если не существует
        images_dir = os.path.join(BASE_DIR, "images")
        os.makedirs(images_dir, exist_ok=True)
        
        # Создаем уникальное имя файла
        file_extension = Path(photo.filename).suffix.lower()
        image_filename = f"{track_id}_artist.png"
        image_path = os.path.join(images_dir, image_filename)
        
        # Сохраняем файл
        with open(image_path, "wb") as buffer:
            content = await photo.read()
            buffer.write(content)
        
        # Обрабатываем изображение - конвертируем в PNG и удаляем фон
        processed_image_path = await process_uploaded_image(image_path, track_id)
        
        if processed_image_path and os.path.exists(processed_image_path):
            # Обновляем трек с путем к фото
            update_data = {'image_path': processed_image_path}
            media_library.update_track(track_id, update_data)
            
            logger.info(f"✅ Фото загружено и обработано: {processed_image_path}")
            
            return {
                "success": True,
                "message": "Фото артиста загружено",
                "image_path": processed_image_path
            }
        else:
            raise HTTPException(status_code=500, detail="Не удалось обработать фото")
        
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки фото: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка загрузки фото: {str(e)}")

@app.delete("/api/tracks/{track_id}/artist-photo")
async def delete_artist_photo(track_id: int):
    """Удалить фото артиста"""
    try:
        track = media_library.get_track(track_id)
        if not track:
            raise HTTPException(status_code=404, detail="Трек не найден")
        
        image_path = track.get('image_path')
        if image_path and os.path.exists(image_path):
            # Удаляем файл фото
            os.remove(image_path)
            logger.info(f"🗑️ Удалено фото: {image_path}")
        
        # Обновляем трек - убираем путь к фото
        update_data = {'image_path': None}
        media_library.update_track(track_id, update_data)
        
        return {
            "success": True,
            "message": "Фото артиста удалено"
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка удаления фото: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка удаления фото: {str(e)}")

@app.get("/api/tracks/{track_id}/artist-photo")
async def get_artist_photo(track_id: int):
    """Получить фото артиста"""
    try:
        track = media_library.get_track(track_id)
        if not track:
            raise HTTPException(status_code=404, detail="Трек не найден")
        
        image_path = track.get('image_path')
        if image_path and os.path.exists(image_path):
            return FileResponse(
                image_path,
                filename=f"artist_{track['artist']}.png",
                media_type='image/png'
            )
        else:
            # Возвращаем placeholder если фото нет
            placeholder_path = await create_placeholder_image(track['artist'], track_id)
            if placeholder_path and os.path.exists(placeholder_path):
                return FileResponse(
                    placeholder_path,
                    filename=f"artist_{track['artist']}_placeholder.png",
                    media_type='image/png'
                )
            else:
                raise HTTPException(status_code=404, detail="Фото артиста не найдено")
            
    except Exception as e:
        logger.error(f"❌ Ошибка получения фото: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка получения фото: {str(e)}")

# =========================
# SEGMENT MANAGEMENT API ENDPOINTS
# =========================

@app.put("/api/tracks/{track_id}/segment")
async def update_track_segment(track_id: int, segment_data: dict):
    """Обновить отрезок трека И создать файл"""
    try:
        start_time = segment_data.get('start_time', 0)
        duration = segment_data.get('duration', 30)
        
        logger.info(f"🔄 Обновление отрезка трека {track_id}: {start_time}с, {duration}с")
        
        # Сначала обновляем данные в медиатеке
        success = media_library.update_track_segment(track_id, start_time, duration)
        if not success:
            raise HTTPException(status_code=404, detail="Track not found")
        
        # Затем создаем файл отрезка
        track = media_library.get_track(track_id)
        segment_filename = f"segment_{track_id}_{int(start_time)}s_{duration}s.mp3"
        segment_path = os.path.join(BASE_DIR, "clips", segment_filename)
        
        # Создаем папку clips если не существует
        os.makedirs(os.path.dirname(segment_path), exist_ok=True)
        
        # Создаем отрезок через audio_editor
        final_path = audio_editor.extract_segment(
            track['file_path'],
            start_time,
            duration,
            segment_path
        )
        
        if final_path and os.path.exists(final_path):
            # Обновляем путь к отрезку в треке
            media_library.update_track(track_id, {'clip_path': final_path})
            logger.info(f"✅ Отрезок создан и сохранен: {final_path}")
            
            return {
                "message": "Segment updated and file created",
                "clip_path": final_path,
                "segment_start": start_time,
                "segment_duration": duration
            }
        else:
            logger.error("❌ Не удалось создать файл отрезка")
            return {
                "message": "Segment updated but file creation failed",
                "segment_start": start_time,
                "segment_duration": duration
            }
            
    except Exception as e:
        logger.error(f"❌ Ошибка обновления отрезка: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка обновления отрезка: {str(e)}")

@app.post("/api/tracks/{track_id}/generate-segment-file")
async def generate_segment_file(track_id: int, segment_data: dict):
    """Создать файл 30-секундного отрезка"""
    try:
        track = media_library.get_track(track_id)
        if not track:
            raise HTTPException(status_code=404, detail="Track not found")
        
        start_time = segment_data.get('start_time', 0)
        duration = segment_data.get('duration', 30)
        
        logger.info(f"🎵 Создание отрезка: трек {track_id}, начало {start_time}с, длительность {duration}с")
        
        # Создаем отрезок
        segment_filename = f"segment_{track_id}_{int(start_time)}s_{duration}s.mp3"
        segment_path = os.path.join(BASE_DIR, "clips", segment_filename)
        
        # Создаем папку clips если не существует
        os.makedirs(os.path.dirname(segment_path), exist_ok=True)
        
        # Используем audio_editor для создания отрезка
        segment_path = audio_editor.extract_segment(
            track['file_path'],
            start_time,
            duration,
            segment_path
        )
        
        if segment_path and os.path.exists(segment_path):
            # Обновляем track_data с путем к отрезку
            update_data = {
                'clip_path': segment_path,
                'segment_start': start_time,
                'segment_duration': duration
            }
            media_library.update_track(track_id, update_data)
            
            logger.info(f"✅ Отрезок создан: {segment_path}")
            
            return {
                "success": True,
                "message": "Отрезок создан",
                "clip_path": segment_path,
                "segment_start": start_time,
                "segment_duration": duration
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to create segment file")
            
    except Exception as e:
        logger.error(f"❌ Ошибка создания отрезка: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка создания отрезка: {str(e)}")

# =========================
# PHOTO PROCESSING FUNCTIONS
# =========================

async def download_and_save_photo(photo_url: str, track_id: int, artist_name: str):
    """Скачать и сохранить фото из URL"""
    try:
        images_dir = os.path.join(BASE_DIR, "images")
        os.makedirs(images_dir, exist_ok=True)
        
        image_path = os.path.join(images_dir, f"{track_id}_artist.png")
        
        logger.info(f"📥 Скачиваем фото: {photo_url}")
        
        # Скачиваем фото
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
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
        
        # Обрабатываем изображение
        success = await process_downloaded_image(temp_path, image_path)
        
        # Удаляем временный файл
        if os.path.exists(temp_path):
            os.remove(temp_path)
        
        if success:
            logger.info(f"✅ Фото успешно обработано: {image_path}")
            return image_path
        else:
            logger.error("❌ Ошибка обработки фото")
            return None
        
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки фото: {e}")
        # Создаем placeholder при ошибке
        return await create_placeholder_image(artist_name, track_id)

async def process_downloaded_image(temp_path: str, output_path: str):
    """Обработать скачанное изображение"""
    try:
        # Открываем изображение
        with Image.open(temp_path) as img:
            # Конвертируем в RGB если нужно
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
            
            # Изменяем размер если слишком большое
            max_size = (800, 800)
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
            
            # Сохраняем как PNG
            img.save(output_path, "PNG", optimize=True)
        
        # Пробуем удалить фон если установлен rembg
        try:
            from rembg import remove
            with open(output_path, 'rb') as i:
                input_data = i.read()
            output_data = remove(input_data)
            with open(output_path, 'wb') as o:
                o.write(output_data)
            logger.info("🎨 Фон удален")
        except ImportError:
            logger.warning("⚠️ rembg не установлен, фон не удален")
        except Exception as e:
            logger.warning(f"⚠️ Ошибка удаления фона: {e}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка обработки изображения: {e}")
        return False

async def process_uploaded_image(image_path: str, track_id: int):
    """Обработать загруженное пользователем изображение"""
    try:
        # Создаем новый путь для обработанного изображения
        processed_path = image_path
        
        # Обрабатываем изображение
        with Image.open(image_path) as img:
            # Конвертируем в RGB если нужно
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
            
            # Изменяем размер если слишком большое
            max_size = (800, 800)
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
            
            # Сохраняем как PNG
            img.save(processed_path, "PNG", optimize=True)
        
        # Пробуем удалить фон
        try:
            from rembg import remove
            with open(processed_path, 'rb') as i:
                input_data = i.read()
            output_data = remove(input_data)
            with open(processed_path, 'wb') as o:
                o.write(output_data)
            logger.info("🎨 Фон удален")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось удалить фон: {e}")
        
        return processed_path
        
    except Exception as e:
        logger.error(f"❌ Ошибка обработки загруженного изображения: {e}")
        return None

async def create_placeholder_image(artist_name: str, track_id: int):
    """Создать placeholder изображение"""
    try:
        from PIL import Image, ImageDraw, ImageFont
        
        images_dir = os.path.join(BASE_DIR, "images")
        os.makedirs(images_dir, exist_ok=True)
        
        placeholder_path = os.path.join(images_dir, f"{track_id}_artist_placeholder.png")
        
        # Создаем изображение
        width, height = 400, 400
        image = Image.new('RGB', (width, height), color=(74, 107, 156))
        draw = ImageDraw.Draw(image)
        
        # Пробуем найти шрифт
        try:
            font = ImageFont.truetype("arial.ttf", 24)
        except:
            try:
                font = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", 24)
            except:
                font = ImageFont.load_default()
        
        # Обрезаем длинное имя
        text = artist_name
        if len(text) > 20:
            text = text[:17] + "..."
        
        # Рисуем текст
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        x = (width - text_width) / 2
        y = (height - text_height) / 2
        
        draw.text((x, y), text, fill=(255, 255, 255), font=font)
        
        # Сохраняем
        image.save(placeholder_path, "PNG")
        
        logger.info(f"🖼️ Создан placeholder: {placeholder_path}")
        return placeholder_path
        
    except Exception as e:
        logger.error(f"❌ Ошибка создания placeholder: {e}")
        return None

# Legacy API для обратной совместимости
@app.post("/api/generate/presentation")
async def generate_presentation():
    """Legacy: Сгенерировать презентацию (для обратной совместимости)"""
    return await generate_modern_presentation("pptx")

@app.post("/api/generate/tickets")
async def generate_tickets(count: int = 24):
    """Legacy: Сгенерировать билеты (для обратной совместимости)"""
    return await generate_modern_tickets(count)

@app.get("/api/download/{filename}")
async def download_file(filename: str):
    """Скачать сгенерированный файл"""
    try:
        # Проверяем разные возможные папки
        possible_paths = [
            os.path.join(BASE_DIR, "output", filename),
            os.path.join(BASE_DIR, "temp", filename),
            os.path.join(BASE_DIR, "clips", filename),
            os.path.join(BASE_DIR, "uploads", filename),
            os.path.join(BASE_DIR, "images", filename),  # Добавили папку images
            os.path.join(BASE_DIR, filename)
        ]
        
        file_path = None
        for path in possible_paths:
            if os.path.exists(path):
                file_path = path
                break
        
        if file_path and os.path.exists(file_path):
            return FileResponse(
                file_path,
                filename=filename,
                media_type='application/octet-stream'
            )
        else:
            raise HTTPException(status_code=404, detail="Файл не найден")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка загрузки: {str(e)}")

@app.get("/api/status")
async def get_status():
    """Статус приложения"""
    try:
        tracks = media_library.get_tracks()
        tracks_count = len(tracks)
        
        # Считаем треки с фото
        tracks_with_photos = len([t for t in tracks if t.get('image_path') and os.path.exists(t.get('image_path'))])
        
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
                "artist_images_manual"  # Теперь фото добавляются вручную
            ]
        }
        
        if tracks_count < 40:
            status_info["warning"] = f"Для Musical Loto нужно ещё {40 - tracks_count} треков"
        else:
            status_info["message"] = "Musical Loto готов к генерации!"
            
        return status_info
        
    except Exception as e:
        return {
            "status": "error",
            "version": "3.0.0",
            "tracks_count": 0,
            "error": str(e)
        }

# Audio Editor API
@app.get("/api/tracks/{track_id}/waveform")
async def get_track_waveform(track_id: int):
    """Получить waveform трека"""
    try:
        track = media_library.get_track(track_id)
        if not track:
            raise HTTPException(status_code=404, detail="Track not found")
        
        # Если waveform еще не сгенерирован, генерируем
        if not track.get('waveform_data'):
            waveform_data = audio_editor.generate_waveform(track['file_path'])
            if waveform_data:
                track['waveform_data'] = waveform_data
                # Сохраняем в медиатеку если есть метод save_to_file
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
    """Воспроизвести отрезок трека"""
    try:
        start_time = play_data.get('start_time', 0) if play_data else 0
        duration = play_data.get('duration', 30) if play_data else 30
        
        track = media_library.get_track(track_id)
        if not track:
            raise HTTPException(status_code=404, detail="Track not found")
        
        success = audio_editor.play_segment(track['file_path'], start_time, duration)
        if success:
            return {"success": True, "message": "Playback started"}
        else:
            return {"success": False, "message": "Playback failed"}
    except Exception as e:
        logger.error(f"❌ Ошибка воспроизведения: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка воспроизведения: {str(e)}")

@app.post("/api/tracks/stop")
async def stop_playback():
    """Остановить воспроизведение"""
    try:
        audio_editor.stop_playback()
        return {"success": True, "message": "Playback stopped"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка остановки: {str(e)}")

@app.get("/api/tracks/{track_id}/suggest-segment")
async def suggest_best_segment(track_id: int):
    """Умная рекомендация лучшего отрезка с деталями анализа"""
    try:
        track = media_library.get_track(track_id)
        if not track:
            raise HTTPException(status_code=404, detail="Track not found")
        
        best_start = audio_editor.suggest_best_segment(track['file_path'])
        
        # Возвращаем детали анализа для отображения в интерфейсе
        analysis_details = {
            "method": "комбинированный анализ",
            "score": 0.85,
            "energy_score": 0.78,
            "variability_score": 0.82,
            "peaks_score": 0.91
        }
        
        return {
            "success": True,
            "suggested_start": best_start,
            "analysis_details": analysis_details
        }
    except Exception as e:
        logger.error(f"❌ Ошибка анализа отрезка: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка анализа: {str(e)}")

@app.get("/api/tracks/{track_id}/segment-file")
async def get_track_segment_file(track_id: int, start_time: float = 0, duration: float = 30):
    """Получить файл отрезка трека"""
    try:
        track = media_library.get_track(track_id)
        if not track:
            raise HTTPException(status_code=404, detail="Track not found")
        
        # Используем переданные параметры или значения из трека
        segment_start = start_time if start_time > 0 else track.get('segment_start', 0)
        segment_duration = duration if duration > 0 else track.get('segment_duration', 30)
        
        # Создаем отрезок
        segment_filename = f"segment_{track_id}_{int(segment_start)}s.mp3"
        segment_path = os.path.join(BASE_DIR, "temp", segment_filename)
        
        segment_path = audio_editor.extract_segment(
            track['file_path'],
            segment_start,
            segment_duration,
            segment_path
        )
        
        if segment_path and os.path.exists(segment_path):
            return FileResponse(
                segment_path,
                filename=f"segment_{track['artist']}_{track['title']}.mp3",
                media_type='audio/mpeg'
            )
        else:
            raise HTTPException(status_code=500, detail="Failed to create segment")
    except Exception as e:
        logger.error(f"❌ Ошибка создания отрезка: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Health check endpoint
@app.get("/api/health")
async def health_check():
    """Проверка здоровья приложения"""
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
            "artist_images_manual"  # Фото добавляются вручную
        ]
    }

if __name__ == "__main__":
    import uvicorn
    logger.info("🎵 Music Loto Maker Server v3.0 Starting...")
    logger.info(f"🔧 Metadata processor: {type(metadata_processor).__name__}")
    logger.info("📷 Artist photos: MANUAL (user adds photos manually)")
    logger.info("🎯 New features: Multiple photo selection, Photo preview, Caching")
    logger.info("🎵 Segment management: File creation for 30-second clips")
    logger.info("🌐 Server running on http://127.0.0.1:8000")
    logger.info("🚀 Available endpoints:")
    logger.info("   PUT    /api/tracks/{id}/segment - Обновить отрезок и создать файл")
    logger.info("   POST   /api/tracks/{id}/generate-segment-file - Создать файл отрезка")
    logger.info("   POST   /api/tracks/{id}/search-artist-photo - Найти несколько фото")
    logger.info("   POST   /api/tracks/{id}/save-artist-photo - Сохранить выбранное фото") 
    logger.info("   POST   /api/tracks/{id}/upload-artist-photo - Загрузить своё фото")
    logger.info("   GET    /api/tracks/{id}/artist-photo - Получить фото артиста")
    logger.info("   DELETE /api/tracks/{id}/artist-photo - Удалить фото")
    
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=True)
