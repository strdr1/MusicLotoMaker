from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
import os
import logging
import json
from pathlib import Path
import zipfile
from PyPDF2 import PdfMerger

logger = logging.getLogger(__name__)

router = APIRouter()

# Глобальные переменные для зависимостей
media_library = None
ticket_gen = None

def set_dependencies(media_lib, ticket_generator):
    """Установка зависимостей из основного приложения"""
    global media_library, ticket_gen
    media_library = media_lib
    ticket_gen = ticket_generator
    logger.info("✅ Dependencies set in tickets router")

@router.post("/api/tickets/generate")
async def generate_tickets_endpoint(payload: dict):
    """Генерирует билеты с прогрессом"""
    logger.info("🎫 === Генерация билетов ===")
    
    try:
        count = int(payload.get("count", 10))
        design = payload.get("design", {})
        
        logger.info(f"🎫 Параметры: {count} билетов")
        
        if count < 1 or count > 100:
            raise HTTPException(status_code=400, detail="Количество билетов должно быть от 1 до 100")

        # Проверяем зависимости
        if media_library is None or ticket_gen is None:
            raise HTTPException(status_code=500, detail="Генератор билетов не инициализирован")

        # Получаем треки
        tracks = []
        if hasattr(media_library, 'get_tracks'):
            tracks = media_library.get_tracks()
        elif hasattr(media_library, 'tracks'):
            tracks = media_library.tracks
        elif isinstance(media_library, list):
            tracks = media_library
        
        logger.info(f"🎫 Найдено треков: {len(tracks)}")
        
        if not tracks:
            raise HTTPException(status_code=400, detail="Нет треков в медиатеке")

        if len(tracks) < 36:
            raise HTTPException(status_code=400, 
                              detail=f"Недостаточно треков. Нужно 36, доступно {len(tracks)}")

        # Генерируем билеты
        logger.info("🎫 Запуск генерации билетов...")
        generation_result = ticket_gen.generate_modern_tickets(
            tracks=tracks, 
            count=count, 
            design=design
        )
        
        if not generation_result.get("success"):
            error_msg = generation_result.get("message", "Неизвестная ошибка")
            raise HTTPException(status_code=500, detail=error_msg)
        
        # Проверяем что файл создан
        file_path = generation_result.get("file_path")
        if not file_path or not os.path.exists(file_path):
            logger.error(f"🎫 Файл не найден: {file_path}")
            raise HTTPException(status_code=500, detail="Файл билетов не создан")

        logger.info(f"🎫 ✅ Билеты сгенерированы: {file_path}")
        
        return {
            "success": True,
            "message": f"Сгенерировано {count} билетов",
            "zip_file": generation_result.get("zip_file"),
            "download_url": generation_result.get("download_url"),
            "tickets_count": count,
            "tracks_used": len(tracks)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("🎫 Ошибка генерации билетов")
        raise HTTPException(status_code=500, detail=f"Ошибка генерации: {str(e)}")

@router.get("/api/tickets/download/{filename}")
async def download_ticket_file(filename: str):
    """Скачивание файлов билетов"""
    logger.info(f"📥 Скачивание файла: {filename}")
    
    if not filename.endswith(('.pdf', '.zip')) or '..' in filename:
        raise HTTPException(status_code=400, detail="Некорректное имя файла")
    
    # Ищем файл в разных возможных местах
    possible_paths = [
        os.path.join("output", filename),
        os.path.join("./output", filename),
        filename
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            logger.info(f"📥 Файл найден: {path}")
            
            # Определяем MIME тип
            media_type = "application/zip" if filename.endswith('.zip') else "application/pdf"
                
            return FileResponse(
                path, 
                media_type=media_type,
                filename=filename,
                headers={"Content-Disposition": f"attachment; filename={filename}"}
            )
    
    logger.error(f"📥 Файл не найден: {filename}")
    raise HTTPException(status_code=404, detail="Файл не найден")

@router.get("/api/tickets/status")
async def tickets_status():
    """Статус билетов"""
    tracks_count = 0
    if media_library:
        if hasattr(media_library, 'get_tracks'):
            tracks = media_library.get_tracks()
            tracks_count = len(tracks) if tracks else 0
        elif hasattr(media_library, 'tracks'):
            tracks_count = len(media_library.tracks)
    
    return {
        "status": "ready" if media_library and ticket_gen else "not_initialized",
        "tracks_count": tracks_count,
        "ready_for_generation": tracks_count >= 36,
        "min_tracks_required": 36,
        "tracks_available": tracks_count
    }