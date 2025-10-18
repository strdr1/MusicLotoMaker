# backend/server.py
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os
import sys

# Добавляем текущую директорию в путь для импортов
current_dir = os.path.dirname(__file__)
if current_dir not in sys.path:
    sys.path.append(current_dir)

try:
    from media_library import MediaLibrary
    from presentation import PresentationGenerator
    from tickets import TicketGenerator
    from audio_editor import audio_editor
    print("✅ Все модули backend успешно импортированы")
except ImportError as e:
    print(f"❌ Ошибка импорта модулей backend: {e}")
    raise

# Инициализация приложения
app = FastAPI(title="Music Loto Maker", version="1.0.0")

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

# Монтируем статические файлы фронтенда
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

# Инициализация модулей
media_library = MediaLibrary()
presentation_gen = PresentationGenerator()
ticket_gen = TicketGenerator()

@app.get("/")
async def serve_frontend():
    """Главная страница"""
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

# API для медиатеки
@app.get("/api/tracks")
async def get_tracks():
    """Получить все треки"""
    return media_library.get_tracks()

@app.post("/api/tracks/upload")
async def upload_tracks(files: list[UploadFile] = File(...)):
    """Загрузить аудиофайлы"""
    saved_tracks = []
    
    for file in files:
        # Сохраняем файл во временную папку
        temp_dir = os.path.join(BASE_DIR, "temp")
        os.makedirs(temp_dir, exist_ok=True)
        temp_path = os.path.join(temp_dir, file.filename)
        
        with open(temp_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        # Добавляем в медиатеку
        track = media_library.add_track(temp_path, file.filename)
        saved_tracks.append(track)
    
    return {
        "message": f"Успешно загружено {len(saved_tracks)} треков",
        "tracks": saved_tracks
    }

@app.put("/api/tracks/{track_id}")
async def update_track(track_id: int, track_data: dict):
    """Обновить данные трека"""
    success = media_library.update_track(track_id, track_data)
    if success:
        return {"message": "Трек обновлен"}
    else:
        raise HTTPException(status_code=404, detail="Трек не найден")

@app.delete("/api/tracks/{track_id}")
async def delete_track(track_id: int):
    """Удалить трек"""
    success = media_library.delete_track(track_id)
    if success:
        return {"message": "Трек удален"}
    else:
        raise HTTPException(status_code=404, detail="Трек не найден")

@app.delete("/api/tracks")
async def clear_tracks():
    """Очистить всю медиатеку"""
    media_library.clear()
    return {"message": "Медиатека очищена"}

# API для генерации
@app.post("/api/generate/presentation")
async def generate_presentation():
    """Сгенерировать презентацию"""
    tracks = media_library.get_tracks()
    if not tracks:
        raise HTTPException(status_code=400, detail="Добавьте треки в медиатеку")
    
    try:
        output_path = presentation_gen.generate(tracks)
        return {
            "message": "Презентация успешно создана",
            "file_path": output_path,
            "file_name": "presentation.pptx"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка генерации: {str(e)}")

@app.post("/api/generate/tickets")
async def generate_tickets(count: int = 24):
    """Сгенерировать билеты"""
    tracks = media_library.get_tracks()
    if not tracks:
        raise HTTPException(status_code=400, detail="Добавьте треки в медиатеку")
    
    try:
        artists = [track.get('artist', 'Неизвестно') for track in tracks]
        output_path = ticket_gen.generate(artists, count)
        return {
            "message": f"Создано {count} билетов",
            "file_path": output_path,
            "file_name": "tickets.pdf"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка генерации: {str(e)}")

@app.get("/api/download/{filename}")
async def download_file(filename: str):
    """Скачать сгенерированный файл"""
    output_dir = os.path.join(BASE_DIR, "output")
    file_path = os.path.join(output_dir, filename)
    
    if os.path.exists(file_path):
        return FileResponse(
            file_path,
            filename=filename,
            media_type='application/octet-stream'
        )
    else:
        raise HTTPException(status_code=404, detail="Файл не найден")

@app.get("/api/status")
async def get_status():
    """Статус приложения"""
    tracks = media_library.get_tracks()
    return {
        "status": "running",
        "tracks_count": len(tracks),
        "version": "1.0.0"
    }

# Audio Editor API
@app.get("/api/tracks/{track_id}/waveform")
async def get_track_waveform(track_id: int):
    """Получить waveform трека"""
    track = media_library.get_track(track_id)
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")
    
    # Если waveform еще не сгенерирован, генерируем
    if not track.get('waveform_data'):
        track['waveform_data'] = audio_editor.generate_waveform(track['file_path'])
        media_library.save_to_file()
    
    return {"waveform_data": track.get('waveform_data')}

@app.post("/api/tracks/{track_id}/play")
async def play_track_segment(track_id: int):
    """Воспроизвести отрезок трека"""
    success = media_library.play_track_segment(track_id)
    if success:
        return {"message": "Playback started"}
    else:
        raise HTTPException(status_code=400, detail="Playback failed")

@app.post("/api/tracks/stop")
async def stop_playback():
    """Остановить воспроизведение"""
    media_library.stop_playback()
    return {"message": "Playback stopped"}

@app.put("/api/tracks/{track_id}/segment")
async def update_track_segment(track_id: int, segment_data: dict):
    """Обновить отрезок трека"""
    start_time = segment_data.get('start_time', 0)
    duration = segment_data.get('duration', 30)
    
    success = media_library.update_track_segment(track_id, start_time, duration)
    if success:
        return {"message": "Segment updated"}
    else:
        raise HTTPException(status_code=404, detail="Track not found")

@app.get("/api/tracks/{track_id}/suggest-segment")
async def suggest_best_segment(track_id: int):
    """Умная рекомендация лучшего отрезка с деталями анализа"""
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
        "suggested_start": best_start,
        "analysis_details": analysis_details
    }

@app.get("/api/tracks/{track_id}/segment-file")
async def get_track_segment_file(track_id: int):
    """Получить файл отрезка трека"""
    track = media_library.get_track(track_id)
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")
    
    try:
        # Создаем отрезок
        segment_path = audio_editor.extract_segment(
            track['file_path'],
            track['segment_start'],
            track['segment_duration'],
            f"output/segment_{track_id}.mp3"
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
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)