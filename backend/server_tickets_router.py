# backend/server_tickets_router.py
from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import FileResponse
import os
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# Глобальные переменные для зависимостей - объявляем без значений
media_library = None
ticket_gen = None

def set_dependencies(media_lib, ticket_generator):
    """Установка зависимостей из основного приложения"""
    global media_library, ticket_gen
    media_library = media_lib
    ticket_gen = ticket_generator

@router.post("/api/tickets/generate")
async def generate_tickets_endpoint(payload: dict = Body(...)):
    """
    Ожидает JSON:
    {
      "count": 10,
      "design": { ... }  # опционально
    }
    Возвращает: { "success": True, "file": "/api/tickets/download/filename.pdf" }
    """
    try:
        count = int(payload.get("count", 10))
        if count < 1:
            raise HTTPException(status_code=400, detail="count must be >= 1")
        if count > 100:
            raise HTTPException(status_code=400, detail="count max 100")

        design = payload.get("design", {})

        # Проверяем инициализацию зависимостей
        if media_library is None or ticket_gen is None:
            raise HTTPException(status_code=500, detail="Ticket generator not initialized. Call set_dependencies() first.")

        # Получаем треки
        tracks = []
        if hasattr(media_library, 'get_tracks'):
            tracks = media_library.get_tracks()
        elif hasattr(media_library, 'tracks'):
            tracks = media_library.tracks
        elif isinstance(media_library, list):
            tracks = media_library
        else:
            raise HTTPException(status_code=500, detail="Media library doesn't provide tracks")

        if not tracks:
            raise HTTPException(status_code=400, detail="Нет треков в медиатеке")

        logger.info(f"Generating {count} tickets from {len(tracks)} tracks")

        # Генерируем билеты
        output_path = ticket_gen.generate_modern_tickets(tracks, count, design)
        filename = os.path.basename(output_path)
        
        return {
            "success": True, 
            "file": f"/api/tickets/download/{filename}",
            "filename": filename,
            "tracks_used": len(tracks),
            "tickets_generated": count
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Ошибка генерации билетов")
        raise HTTPException(status_code=500, detail=f"Ошибка генерации: {str(e)}")

@router.get("/api/tickets/download/{filename}")
async def download_ticket_file(filename: str):
    """Скачивание сгенерированного файла билетов"""
    # Безопасная проверка имени файла
    if not filename.endswith('.pdf') or '..' in filename or '/' in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    
    # Проверяем разные возможные пути
    possible_paths = [
        os.path.join("output", filename),
        os.path.join("./output", filename),
        filename  # на случай если путь уже полный
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            logger.info(f"Serving file: {path}")
            return FileResponse(
                path, 
                media_type="application/pdf", 
                filename=filename,
                headers={"Content-Disposition": f"inline; filename={filename}"}
            )
    
    logger.error(f"File not found: {filename}")
    raise HTTPException(status_code=404, detail="File not found")

# Альтернативный endpoint для обратной совместимости
@router.get("/download/{filename}")
async def download_file_legacy(filename: str):
    return await download_ticket_file(filename)

# Endpoint для проверки статуса
@router.get("/api/tickets/status")
async def tickets_status():
    """Проверка статуса генератора билетов"""
    return {
        "status": "ready" if media_library and ticket_gen else "not_initialized",
        "media_library_available": media_library is not None,
        "ticket_generator_available": ticket_gen is not None,
        "tracks_count": len(media_library.get_tracks()) if media_library and hasattr(media_library, 'get_tracks') else 0
    }