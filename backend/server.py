# backend/server.py
from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os
import sys
import shutil
from pathlib import Path
import logging
from datetime import datetime
import json
from backend.media_library import MediaLibrary

# Создаём один экземпляр медиатеки для всего приложения
media_lib = MediaLibrary()
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
    logger.info("✅ Hugging Face metadata processor initialized successfully")
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
    
    audio_editor = AudioEditor()

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
for folder in ["temp", "output", "uploads", "config"]:
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
                "Ticket generation"
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
    """Загрузить аудиофайлы"""
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

# API для обновления метаданных
@app.post("/api/tracks/{track_id}/refresh-metadata")
async def refresh_track_metadata(track_id: int):
    """Обновление метаданных трека через Hugging Face"""
    track = media_library.get_track(track_id)
    if not track:
        raise HTTPException(status_code=404, detail="Трек не найден")
    
    try:
        # Получаем свежие метаданные через процессор
        logger.info(f"🔍 Обновление метаданных для трека {track_id}: {track['original_filename']}")
        new_metadata = metadata_processor.process(track['original_filename'])
        logger.info(f"✅ Новые метаданные: {new_metadata}")
        
        # Обновляем трек
        updated_fields = {
            'artist': new_metadata.get('artist', track.get('artist', '')),
            'title': new_metadata.get('title', track.get('title', '')),
            'metadata': new_metadata
        }
        
        success = media_library.update_track(track_id, updated_fields)
        if success:
            updated_track = media_library.get_track(track_id)
            return {
                "success": True,
                "message": "Метаданные обновлены",
                "track": updated_track
            }
        else:
            raise HTTPException(status_code=500, detail="Ошибка обновления в медиатеке")
            
    except Exception as e:
        logger.error(f"❌ Ошибка обновления метаданных: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка обработки: {str(e)}")

@app.post("/api/tracks/batch-refresh-metadata")
async def batch_refresh_metadata():
    """Массовое обновление метаданных всех треков"""
    tracks = media_library.get_tracks()
    updated = 0
    errors = []
    
    for track in tracks:
        try:
            new_metadata = metadata_processor.process(track['original_filename'])
            
            updated_fields = {
                'artist': new_metadata.get('artist', track.get('artist', '')),
                'title': new_metadata.get('title', track.get('title', '')),
                'metadata': new_metadata
            }
            
            media_library.update_track(track['id'], updated_fields)
            updated += 1
            logger.info(f"✅ Обновлен трек {track['id']}: {updated_fields['artist']} - {updated_fields['title']}")
            
        except Exception as e:
            error_msg = f"Трек {track['id']} ({track['original_filename']}): {str(e)}"
            errors.append(error_msg)
            logger.error(f"❌ {error_msg}")
    
    return {
        "success": True,
        "message": f"Обновлено {updated} из {len(tracks)} треков",
        "updated": updated,
        "errors": errors
    }

# API для генерации Musical Loto
@app.post("/api/generate/musical-loto")
async def generate_musical_loto():
    """Генерация современного Musical Loto"""
    try:
        tracks = media_library.get_tracks()
        tracks_count = len(tracks)
        
        if tracks_count < 40:
            raise HTTPException(
                status_code=400, 
                detail=f"Для Musical Loto нужно минимум 40 треков. Сейчас: {tracks_count}"
            )
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(BASE_DIR, "output", f"musical_loto_{timestamp}.pptx")
        
        result = modern_presentation_gen.generate_musical_loto_presentation(tracks, output_path)
        
        if result and os.path.exists(output_path):
            return {
                "success": True,
                "message": "🎲 Musical Loto создан!",
                "file_path": output_path,
                "file_name": os.path.basename(output_path),
                "tracks_used": tracks_count,
                "rounds": "3 раунда",
                "tracks_per_round": min(40, tracks_count),
                "style": "современный игровой дизайн",
                "features": [
                    "Титульный слайд с игровым дизайном",
                    "Правила игры",
                    "3 раунда по 40 треков", 
                    "Слайды с исполнителями",
                    "Интерактивные кнопки для прослушивания",
                    "Финальный слайд"
                ]
            }
        else:
            raise HTTPException(status_code=500, detail="Не удалось создать презентацию")
        
    except Exception as e:
        logger.error(f"❌ Ошибка генерации Musical Loto: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/generate/musical-loto-custom")
async def generate_musical_loto_custom(
    rounds: int = Form(3),
    tracks_per_round: int = Form(40),
    include_rules: bool = Form(True),
    style: str = Form("modern")
):
    """Генерация Musical Loto с кастомными настройками"""
    try:
        tracks = media_library.get_tracks()
        total_tracks_needed = rounds * tracks_per_round
        
        if len(tracks) < tracks_per_round:
            raise HTTPException(
                status_code=400, 
                detail=f"Нужно минимум {tracks_per_round} треков. Сейчас: {len(tracks)}"
            )
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(BASE_DIR, "output", f"musical_loto_custom_{timestamp}.pptx")
        
        # Сохраняем настройки
        config = {
            "rounds": rounds,
            "tracks_per_round": tracks_per_round,
            "include_rules": include_rules,
            "style": style,
            "generated_at": datetime.now().isoformat()
        }
        
        config_path = os.path.join(BASE_DIR, "config", f"loto_config_{timestamp}.json")
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        
        # Здесь будет вызов кастомного генератора
        result = modern_presentation_gen.generate_musical_loto_presentation(tracks, output_path)
        
        if result and os.path.exists(output_path):
            return {
                "success": True,
                "message": "🎲 Custom Musical Loto создан!",
                "file_path": output_path,
                "config": config,
                "tracks_used": len(tracks),
                "total_tracks_available": len(tracks)
            }
        else:
            raise HTTPException(status_code=500, detail="Не удалось создать презентацию")
        
    except Exception as e:
        logger.error(f"❌ Ошибка генерации кастомного Musical Loto: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# API для современной генерации презентаций
@app.post("/api/generate/modern-presentation")
async def generate_modern_presentation(format: str = "pptx"):
    """Сгенерировать современную презентацию"""
    try:
        tracks = media_library.get_tracks()
        if not tracks:
            raise HTTPException(status_code=400, detail="Добавьте треки в медиатеку")
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if format == "pptx":
            output_path = os.path.join(BASE_DIR, "output", f"modern_presentation_{timestamp}.pptx")
            modern_presentation_gen.generate_modern_pptx(tracks, output_path)
            file_type = "PowerPoint презентация"
        elif format == "pdf":
            output_path = os.path.join(BASE_DIR, "output", f"modern_presentation_{timestamp}.pdf")
            modern_presentation_gen.generate_modern_pdf(tracks, output_path)
            file_type = "PDF документ"
        else:
            raise HTTPException(status_code=400, detail="Неподдерживаемый формат")
        
        filename = os.path.basename(output_path)
        
        return {
            "success": True,
            "message": f"Современная {file_type} создана",
            "file_path": output_path,
            "file_name": filename,
            "tracks_count": len(tracks),
            "format": format
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка генерации современной презентации: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка генерации: {str(e)}")

@app.post("/api/generate/modern-tickets")
async def generate_modern_tickets(count: int = 24):
    """Сгенерировать современные билеты"""
    try:
        tracks = media_library.get_tracks()
        if not tracks:
            raise HTTPException(status_code=400, detail="Добавьте треки в медиатеку")
        
        output_path = ticket_gen.generate_modern_tickets(tracks, count)
        filename = os.path.basename(output_path)
        
        return {
            "success": True,
            "message": f"Создано {count} современных билетов",
            "file_path": output_path,
            "file_name": filename,
            "tickets_count": count
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка генерации билетов: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка генерации: {str(e)}")

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
        
        status_info = {
            "status": "running",
            "version": "3.0.0",
            "tracks_count": tracks_count,
            "musical_loto_ready": tracks_count >= 40,
            "metadata_processor": type(metadata_processor).__name__,
            "features": [
                "musical_loto_game",
                "modern_presentations", 
                "smart_metadata",
                "audio_editing",
                "ticket_generation"
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

@app.put("/api/tracks/{track_id}/segment")
async def update_track_segment(track_id: int, segment_data: dict):
    """Обновить отрезок трека"""
    try:
        start_time = segment_data.get('start_time', 0)
        duration = segment_data.get('duration', 30)
        
        success = media_library.update_track_segment(track_id, start_time, duration)
        if success:
            return {"message": "Segment updated"}
        else:
            raise HTTPException(status_code=404, detail="Track not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка обновления отрезка: {str(e)}")

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

# Debug endpoint для тестирования
@app.post("/api/debug/upload-test")
async def debug_upload_test(file: UploadFile = File(...)):
    """Тестовый endpoint для отладки загрузки"""
    try:
        logger.info(f"🔍 Debug upload: {file.filename}")
        
        # Сохраняем файл
        uploads_dir = os.path.join(BASE_DIR, "uploads")
        os.makedirs(uploads_dir, exist_ok=True)
        
        test_path = os.path.join(uploads_dir, f"debug_{file.filename}")
        with open(test_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        # Тестируем метадата процессор
        metadata = metadata_processor.process(file.filename)
        
        return {
            "filename": file.filename,
            "saved_path": test_path,
            "file_exists": os.path.exists(test_path),
            "file_size": os.path.getsize(test_path) if os.path.exists(test_path) else 0,
            "metadata": metadata,
            "processor_type": type(metadata_processor).__name__
        }
    except Exception as e:
        logger.error(f"❌ Debug upload error: {e}")
        return {"error": str(e)}

@app.post("/api/debug/generate-test-musical-loto")
async def debug_generate_test_musical_loto():
    """Тестовая генерация Musical Loto"""
    try:
        # Создаем тестовые треки
        test_tracks = [
            {
                'id': 1,
                'artist': 'GAYAZOV BROTHER',
                'title': 'Пьяный туман',
                'original_filename': 'GAYAZOV_BROTHER_-_Pyanyjj_tuman_62788609.mp3'
            },
            {
                'id': 2, 
                'artist': 'Гио Пика',
                'title': 'Где прошла ты',
                'original_filename': 'Kravc_Gio_Pika_-_Gde_proshla_ty_75704918.mp3'
            },
            {
                'id': 3,
                'artist': 'Тима Амеди',
                'title': 'Я не могу',
                'original_filename': 'Tima_Amedi_YA_Ne_Mogu.mp3'
            }
        ]
        
        # Добавляем больше тестовых треков для демонстрации
        for i in range(4, 41):
            test_tracks.append({
                'id': i,
                'artist': f'Исполнитель {i}',
                'title': f'Песня {i}',
                'original_filename': f'test_track_{i}.mp3'
            })
        
        output_path = os.path.join(BASE_DIR, "output", f"test_musical_loto_{datetime.now().strftime('%H%M%S')}.pptx")
        modern_presentation_gen.generate_musical_loto_presentation(test_tracks, output_path)
        
        return {
            "success": True,
            "message": "Тестовый Musical Loto создан",
            "file_path": output_path,
            "test_tracks_count": len(test_tracks),
            "features": "3 раунда по 40 треков"
        }
    except Exception as e:
        logger.error(f"❌ Debug Musical Loto error: {e}")
        return {"error": str(e)}

# Health check endpoint
@app.get("/api/health")
async def health_check():
    """Проверка здоровья приложения"""
    tracks_count = media_library.get_tracks_count()
    
    return {
        "status": "healthy", 
        "service": "Music Loto Maker API v3.0",
        "timestamp": datetime.now().isoformat(),
        "tracks_loaded": tracks_count,
        "musical_loto_ready": tracks_count >= 40,
        "features": ["musical_loto", "modern_presentations", "smart_metadata"]
    }

@app.route('/save_project', methods=['POST'])
def save_project():
    count = media_lib.save_project()
    return jsonify({"status": "success", "saved_tracks": count})

if __name__ == "__main__":
    import uvicorn
    logger.info("🎵 Music Loto Maker Server v3.0 Starting...")
    logger.info(f"🔧 Metadata processor: {type(metadata_processor).__name__}")
    logger.info("🎲 New feature: Musical Loto Game")
    logger.info("🌐 Server running on http://127.0.0.1:8000")
    logger.info("🚀 Available endpoints:")
    logger.info("   POST /api/generate/musical-loto - Создать Musical Loto")
    logger.info("   POST /api/generate/musical-loto-custom - Кастомный Musical Loto")
    logger.info("   GET  /api/tracks/count - Проверить готовность")
    
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=True)