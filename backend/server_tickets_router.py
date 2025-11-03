# backend/server_tickets_router.py
from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import FileResponse
import os
import logging
import zipfile
from pathlib import Path
import json
import shutil

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

        if len(tracks) < 36:
            logger.error(f"🎫 Ошибка: недостаточно треков. Нужно 36, доступно {len(tracks)}")
            raise HTTPException(status_code=400, detail=f"Недостаточно треков. Нужно минимум 36, доступно: {len(tracks)}")

        # Логируем примеры треков
        logger.info("🎫 Примеры треков из медиатеки:")
        for i, track in enumerate(tracks[:3]):
            artist = track.get('artist', 'Unknown')
            title = track.get('title', 'No Title')
            logger.info(f"🎫   {i+1}. Artist: '{artist}', Title: '{title}'")

        logger.info(f"🎫 Генерация {count} билетов из {len(tracks)} треков")

        # Генерируем билеты с поддержкой дизайна
        logger.info("🎫 Запускаем ticket_gen.generate_modern_tickets с дизайном...")
        
        # ВАЖНО: метод generate_modern_tickets возвращает СЛОВАРЬ!
        generation_result = ticket_gen.generate_modern_tickets(
            tracks=tracks, 
            count=count, 
            design=design
        )
        
        logger.info(f"🎫 ✅ Результат генерации: {json.dumps(generation_result, ensure_ascii=False, indent=2)}")
        
        # Проверяем структуру ответа
        if not isinstance(generation_result, dict):
            logger.error(f"🎫 Ошибка: метод вернул не словарь, а {type(generation_result)}")
            raise HTTPException(status_code=500, detail="Некорректный ответ от генератора билетов")
        
        if not generation_result.get("success"):
            error_msg = generation_result.get("message", "Неизвестная ошибка генерации")
            logger.error(f"🎫 Ошибка генерации: {error_msg}")
            raise HTTPException(status_code=500, detail=error_msg)
        
        # Получаем данные из результата
        zip_filename = generation_result.get("zip_file")
        download_url = generation_result.get("download_url")
        file_path = generation_result.get("file_path")
        folder = generation_result.get("folder")
        
        # Проверяем, что ZIP файл существует
        if file_path and os.path.exists(file_path):
            logger.info(f"🎫 Используем готовый ZIP файл: {file_path}")
            
            result = {
                "success": True, 
                "message": f"Сгенерировано {count} билетов",
                "folder": folder,
                "zip_file": zip_filename,
                "download_url": download_url,
                "tickets_count": count,
                "tracks_used": len(tracks)
            }
            
            logger.info(f"🎫 Возвращаем результат: {json.dumps(result, ensure_ascii=False, indent=2)}")
            return result
        
        else:
            logger.error(f"🎫 Ошибка: ZIP файл не найден по пути: {file_path}")
            raise HTTPException(status_code=500, detail="ZIP файл не создан")

    except HTTPException as he:
        logger.error(f"🎫 HTTPException: {he.detail}")
        raise
    except Exception as e:
        logger.exception("🎫 Неожиданная ошибка генерации билетов")
        raise HTTPException(status_code=500, detail=f"Ошибка генерации: {str(e)}")

@router.get("/api/tickets/download/{filename}")
async def download_ticket_file(filename: str):
    """Скачивание билетов - альтернативный endpoint"""
    logger.info(f"📥 === ВЫЗВАН /api/tickets/download/{filename} ===")
    
    # Разрешаем скачивание ZIP файлов
    if not filename.endswith(('.pdf', '.zip')) or '..' in filename or '/' in filename:
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
            
            # Определяем MIME тип
            if filename.endswith('.zip'):
                media_type = "application/zip"
            else:
                media_type = "application/pdf"
                
            return FileResponse(
                path, 
                media_type=media_type,
                filename=filename,
                headers={"Content-Disposition": f"attachment; filename={filename}"}
            )
        else:
            logger.info(f"📥 Файл не найден по пути: {path}")
    
    logger.error(f"📥 Файл не найден ни по одному пути: {filename}")
    raise HTTPException(status_code=404, detail="File not found")

@router.get("/api/tickets/status")
async def tickets_status():
    """Статус билетов"""
    logger.info("📊 === ВЫЗВАН /api/tickets/status ===")
    
    tracks_count = 0
    if media_library:
        if hasattr(media_library, 'get_tracks'):
            tracks = media_library.get_tracks()
            tracks_count = len(tracks) if tracks else 0
        elif hasattr(media_library, 'tracks'):
            tracks_count = len(media_library.tracks)
    
    status = {
        "status": "ready" if media_library and ticket_gen else "not_initialized",
        "media_library_available": media_library is not None,
        "ticket_generator_available": ticket_gen is not None,
        "tracks_count": tracks_count,
        "ready_for_generation": tracks_count >= 36
    }
    logger.info(f"📊 Статус: {status}")
    return status