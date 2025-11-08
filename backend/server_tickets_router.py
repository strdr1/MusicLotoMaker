# tickets_router.py
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
import os
import logging
from concurrent.futures import ThreadPoolExecutor
import asyncio

logger = logging.getLogger(__name__)

router = APIRouter()

media_library = None
ticket_gen = None
active_connections = []

def set_dependencies(media_lib, ticket_generator):
    global media_library, ticket_gen
    media_library = media_lib
    ticket_gen = ticket_generator
    logger.info("✅ Dependencies set in tickets router")

async def send_progress_update(current: int, total: int, message: str):
    progress_data = {
        "type": "progress",
        "current": current,
        "total": total,
        "message": message,
        "percent": int((current / total) * 100) if total > 0 else 0
    }
    disconnected = []
    for connection in active_connections:
        try:
            await connection.send_json(progress_data)
        except Exception as e:
            logger.error(f"❌ Ошибка WebSocket: {e}")
            disconnected.append(connection)
    for conn in disconnected:
        active_connections.remove(conn)

@router.websocket("/ws/tickets/progress")
async def websocket_progress(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    try:
        await websocket.send_json({"type": "connected", "message": "WebSocket подключен"})
        while True:
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        active_connections.remove(websocket)
    except Exception as e:
        logger.error(f"❌ WebSocket error: {e}")
        active_connections.remove(websocket)

@router.post("/api/tickets/generate")
async def generate_tickets_endpoint(payload: dict):
    logger.info("🎫 === Генерация билетов ===")
    try:
        count = int(payload.get("count", 10))
        design = payload.get("design", {})
        if count < 1 or count > 100:
            raise HTTPException(status_code=400, detail="Количество билетов должно быть от 1 до 100")

        if media_library is None or ticket_gen is None:
            raise HTTPException(status_code=500, detail="Генератор не инициализирован")

        # Получаем треки
        tracks = []
        if hasattr(media_library, 'get_tracks'):
            tracks = media_library.get_tracks()
        elif hasattr(media_library, 'tracks'):
            tracks = media_library.tracks
        elif isinstance(media_library, list):
            tracks = media_library

        if not tracks:
            raise HTTPException(status_code=400, detail="Нет треков в медиатеке")
        if len(tracks) < 36:
            raise HTTPException(status_code=400, detail=f"Недостаточно треков. Нужно 36, доступно {len(tracks)}")

        loop = asyncio.get_event_loop()

        def sync_progress_callback(current, total, message):
            asyncio.run_coroutine_threadsafe(
                send_progress_update(current, total, message),
                loop
            )

        await send_progress_update(0, count, "Подготовка к генерации...")

        with ThreadPoolExecutor() as executor:
            generation_result = await loop.run_in_executor(
                executor,
                ticket_gen.generate_modern_tickets,
                tracks,
                count,
                design,
                sync_progress_callback
            )

        if not generation_result.get("success"):
            error_msg = generation_result.get("message", "Неизвестная ошибка")
            await send_progress_update(0, count, f"❌ Ошибка: {error_msg}")
            raise HTTPException(status_code=500, detail=error_msg)

        file_path = generation_result.get("file_path")
        if not file_path or not os.path.exists(file_path):
            await send_progress_update(0, count, "❌ Файл билетов не создан")
            raise HTTPException(status_code=500, detail="Файл билетов не создан")

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
        await send_progress_update(0, 1, f"❌ Ошибка генерации: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка генерации: {str(e)}")

@router.get("/api/tickets/download/{filename}")
async def download_ticket_file(filename: str):
    if not filename.endswith(('.pdf', '.zip')) or '..' in filename:
        raise HTTPException(status_code=400, detail="Некорректное имя файла")
    for base in ["output", "./output", "."]:
        path = os.path.join(base, filename)
        if os.path.exists(path):
            media_type = "application/zip" if filename.endswith('.zip') else "application/pdf"
            return FileResponse(path, media_type=media_type, filename=filename)
    raise HTTPException(status_code=404, detail="Файл не найден")

@router.get("/api/tickets/status")
async def tickets_status():
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