# backend/server_tickets_router.py
from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import FileResponse
import os
import logging
import zipfile
from pathlib import Path
import json

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
    logger.info("🎫 Dependencies set in tickets router")

@router.post("/api/tickets/generate")
async def generate_tickets_endpoint(payload: dict = Body(...)):
    """Генерирует билеты с подробным логированием"""
    logger.info("🎫 === ВЫЗВАН /api/tickets/generate ===")
    logger.info(f"🎫 Полный payload: {json.dumps(payload, ensure_ascii=False, indent=2)}")
    
    try:
        count = int(payload.get("count", 10))
        design = payload.get("design", {})
        
        logger.info(f"🎫 Извлеченные параметры:")
        logger.info(f"🎫   - count: {count}")
        logger.info(f"🎫   - design keys: {list(design.keys())}")
        logger.info(f"🎫   - design details: {design}")
        
        if count < 1:
            logger.error("🎫 Ошибка: count < 1")
            raise HTTPException(status_code=400, detail="count must be >= 1")
        if count > 100:
            logger.error("🎫 Ошибка: count > 100")
            raise HTTPException(status_code=400, detail="count max 100")

        # Проверяем инициализацию зависимостей
        if media_library is None or ticket_gen is None:
            logger.error("🎫 Ошибка: зависимости не инициализированы")
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
            logger.error("🎫 Ошибка: media_library не предоставляет tracks")
            raise HTTPException(status_code=500, detail="Media library doesn't provide tracks")

        logger.info(f"🎫 Найдено треков: {len(tracks)}")
        
        if not tracks:
            logger.error("🎫 Ошибка: нет треков в медиатеке")
            raise HTTPException(status_code=400, detail="Нет треков в медиатеке")

        # Логируем примеры треков
        logger.info("🎫 Примеры треков из медиатеки:")
        for i, track in enumerate(tracks[:3]):
            artist = track.get('artist', 'Unknown')
            title = track.get('title', 'No Title')
            logger.info(f"🎫   {i+1}. Artist: '{artist}', Title: '{title}'")

        logger.info(f"🎫 Генерация {count} билетов из {len(tracks)} треков")

        # Генерируем билеты с поддержкой дизайна
        logger.info("🎫 Запускаем ticket_gen.generate_modern_tickets с дизайном...")
        tickets_folder = ticket_gen.generate_modern_tickets(
            tracks=tracks, 
            count=count, 
            design=design
        )
        
        logger.info(f"🎫 ✅ Билеты сгенерированы в папке: {tickets_folder}")
        
        # Создаем ZIP архив со всеми билетами
        zip_filename = f"tickets_{os.path.basename(tickets_folder)}.zip"
        zip_path = os.path.join("output", zip_filename)
        
        logger.info(f"🎫 Создаем ZIP архив: {zip_path}")
        
        # Создаем ZIP архив
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(tickets_folder):
                for file in files:
                    if file.endswith('.pdf'):
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, tickets_folder)
                        zipf.write(file_path, arcname)
                        logger.debug(f"🎫 Добавлен в ZIP: {file}")
        
        logger.info(f"🎫 ✅ Создан ZIP архив: {zip_path}")
        
        result = {
            "success": True, 
            "folder": tickets_folder,
            "zip_file": f"/api/tickets/download/{zip_filename}",
            "tickets_count": count,
            "tracks_used": len(tracks),
            "files": [f for f in os.listdir(tickets_folder) if f.endswith('.pdf')]
        }
        
        logger.info(f"🎫 Возвращаем результат: {json.dumps(result, ensure_ascii=False, indent=2)}")
        return result

    except HTTPException as he:
        logger.error(f"🎫 HTTPException: {he.detail}")
        raise
    except Exception as e:
        logger.exception("🎫 Неожиданная ошибка генерации билетов")
        raise HTTPException(status_code=500, detail=f"Ошибка генерации: {str(e)}")

@router.get("/api/tickets/download/{filename}")
async def download_ticket_file(filename: str):
    """Скачивание билетов"""
    logger.info(f"📥 === ВЫЗВАН /api/tickets/download/{filename} ===")
    
    if not filename.endswith('.pdf') or '..' in filename or '/' in filename:
        logger.error(f"📥 Неверное имя файла: {filename}")
        raise HTTPException(status_code=400, detail="Invalid filename")
    
    possible_paths = [
        os.path.join("output", filename),
        os.path.join("./output", filename),
        filename
    ]
    
    logger.info(f"📥 Ищем файл по путям: {possible_paths}")
    
    for path in possible_paths:
        if os.path.exists(path):
            logger.info(f"📥 Файл найден: {path}")
            return FileResponse(
                path, 
                media_type="application/pdf", 
                filename=filename,
                headers={"Content-Disposition": f"inline; filename={filename}"}
            )
        else:
            logger.info(f"📥 Файл не найден по пути: {path}")
    
    logger.error(f"📥 Файл не найден ни по одному пути: {filename}")
    raise HTTPException(status_code=404, detail="File not found")

@router.get("/api/tickets/status")
async def tickets_status():
    """Статус билетов"""
    logger.info("📊 === ВЫЗВАН /api/tickets/status ===")
    status = {
        "status": "ready" if media_library and ticket_gen else "not_initialized",
        "media_library_available": media_library is not None,
        "ticket_generator_available": ticket_gen is not None,
        "tracks_count": len(media_library.get_tracks()) if media_library and hasattr(media_library, 'get_tracks') else 0
    }
    logger.info(f"📊 Статус: {status}")
    return status