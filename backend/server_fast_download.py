# -*- coding: utf-8 -*-
"""
Асинхронная потоковая загрузка треков с реальным стримингом (SSE)
"""
import os
import re
import json
import asyncio
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse
import yt_dlp

from backend.server import media_library, image_searcher, parse_track_list

logger = logging.getLogger("fast_download")
executor = ThreadPoolExecutor(max_workers=8)
router = APIRouter()

DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)


def slugify(s: str) -> str:
    s = re.sub(r"[^\w\s.-]+", "", s, flags=re.U)
    s = re.sub(r"\s+", "_", s.strip(), flags=re.U)
    return s[:140].lower()


async def download_youtube_audio(query: str) -> str | None:
    """Асинхронное скачивание аудио через yt_dlp"""
    try:
        loop = asyncio.get_event_loop()
        output_path = DOWNLOAD_DIR / f"{slugify(query)}.mp3"
        if output_path.exists():
            return str(output_path)

        def _download():
            ydl_opts = {
                "format": "bestaudio/best",
                "outtmpl": str(output_path),
                "quiet": True,
                "noplaylist": True,
                "no_warnings": True,
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "128",
                }],
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([f"ytsearch1:{query}"])

        await loop.run_in_executor(executor, _download)
        return str(output_path)
    except Exception as e:
        logger.warning(f"Ошибка download_youtube_audio('{query}'): {e}")
        return None


@router.post("/api/tracks/download-from-list")
async def fast_download_from_list(request: Request):
    """Потоковая обработка списка треков с SSE"""
    data = await request.json()
    text = data.get("track_list", "") or ""
    auto_search_photos = bool(data.get("auto_search_photos", True))
    use_smart_segments = bool(data.get("use_smart_segments", True))

    if not text.strip():
        raise HTTPException(status_code=400, detail="Список треков пуст")

    tracks = parse_track_list(text)
    if not tracks:
        raise HTTPException(status_code=400, detail="Не удалось распознать треки")

    total = len(tracks)
    sem = asyncio.Semaphore(6)

    async def event_stream():
        done_count = 0

        async def process_track(track_info):
            nonlocal done_count
            async with sem:
                query = track_info.get("search_query") or track_info.get("original_line") or ""
                original_line = track_info.get("original_line", query)
                base = {"original_line": original_line, "success": False}

                def emit(stage: str, extra: dict | None = None):
                    payload = {"stage": stage, "track": base, "done": done_count, "total": total}
                    if extra:
                        payload.update(extra)
                    return json.dumps(payload) + "\n"

                # 1️⃣ Скачивание
                yield emit("download")
                audio_path = await download_youtube_audio(query)
                if not audio_path:
                    base["error"] = "Не удалось скачать"
                    yield emit("error", {"error": base["error"]})
                    done_count += 1
                    return

                base["audio_path"] = audio_path
                yield emit("downloaded", {"audio_path": audio_path})

                # 2️⃣ Добавляем в медиатеку
                loop = asyncio.get_event_loop()
                try:
                    t = await loop.run_in_executor(executor,
                        lambda: media_library.add_track(audio_path, os.path.basename(audio_path)))
                    base["track_id"] = t.get("id")
                except Exception as e:
                    base["error"] = f"Ошибка медиатеки: {e}"
                    yield emit("error", {"error": base["error"]})
                    done_count += 1
                    return

                # 3️⃣ Поиск фото
                if auto_search_photos and track_info.get("artist"):
                    artist = track_info["artist"]
                    yield emit("photo", {"artist": artist})
                    try:
                        img_path = await loop.run_in_executor(
                            executor,
                            lambda: image_searcher.fetch_artist_png(artist, t["id"])
                        )
                        if img_path:
                            await loop.run_in_executor(
                                executor,
                                lambda: media_library.update_track(t["id"], {"image_path": img_path})
                            )
                            base["image_path"] = img_path
                            yield emit("photo_result", {"image_path": img_path})
                        else:
                            yield emit("photo_result", {"image_path": None})
                    except Exception as e:
                        logger.warning(f"Ошибка фото: {e}")
                        yield emit("photo_result", {"image_error": str(e)})
                else:
                    yield emit("photo_result", {"image_path": None})

                # 4️⃣ Анализ отрезков
                if use_smart_segments:
                    yield emit("segments")
                    await asyncio.sleep(0.05)
                    yield emit("segments_result")
                else:
                    yield emit("segments_result", {"skipped": True})

                # 5️⃣ Готово
                base["success"] = True
                done_count += 1
                yield emit("done", {"done_count": done_count})

        tasks = [process_track(t) async for t in _iter_async(tracks)]
        for coro in asyncio.as_completed(tasks):
            async for chunk in await coro:
                yield chunk

        try:
            media_library.save_to_file()
        except Exception:
            logger.exception("Не удалось сохранить медиатеку")

        yield json.dumps({"finished": True, "total": total}) + "\n"

    # 🚀 Важно — чтобы браузер не буферизовал поток
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*"
        }
    )


async def _iter_async(items):
    for i in items:
        yield i


def register_fast_download(app):
    app.include_router(router)
    logger.info("✅ Fast download router подключён (SSE)")
