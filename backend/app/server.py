"""FastAPI 應用程式（Phase 2）。

lifespan 於啟動時依 `.env` 建立攝影機/來源/串流器/管線，並在 ThreadPoolExecutor
背景執行緒中持續擷取；關閉時優雅停止並收尾錄影段。
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from .camera import Camera
from .config import settings
from .db.base import engine
from .pipeline import VideoPipeline
from .routers import recording, stream
from .sources import create_source
from .streaming import MJPEGStreamer

logger = logging.getLogger("nvr")


def _configure_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


def _is_realtime_source(url: str) -> bool:
    """synthetic 與本機影片檔需節流到接近即時；webcam/RTSP 由硬體/網路自然限速。"""
    if url == "synthetic":
        return True
    if url.isdigit():
        return False
    if url.startswith(("rtsp://", "rtsps://", "http://", "https://")):
        return False
    return True


@asynccontextmanager
async def lifespan(app: FastAPI):
    _configure_logging()
    loop = asyncio.get_running_loop()

    camera = Camera(id=1, name=settings.camera_name, url=settings.camera_url)
    streamer = MJPEGStreamer(loop)
    source = create_source(
        settings.camera_url,
        fallback_fps=settings.target_fps,
        loop=settings.camera_loop,
        width=settings.frame_width,
        height=settings.frame_height,
    )
    pipeline = VideoPipeline(
        camera=camera,
        source=source,
        streamer=streamer,
        recordings_dir=settings.recordings_dir,
        segment_seconds=settings.segment_seconds,
        fallback_fps=settings.target_fps,
        jpeg_quality=settings.jpeg_quality,
        realtime_pacing=_is_realtime_source(settings.camera_url),
        record_on_start=settings.record_on_start,
    )

    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="capture")
    capture_future = loop.run_in_executor(executor, pipeline.start)

    app.state.pipelines = {camera.id: pipeline}
    app.state.capture_future = capture_future
    logger.info(
        "FastAPI-NVR 啟動：來源=%s 段長=%ds record_on_start=%s",
        settings.camera_url, settings.segment_seconds, settings.record_on_start,
    )

    try:
        yield
    finally:
        pipeline.stop()
        try:
            await capture_future
        except Exception:  # noqa: BLE001 - 收尾期間記錄即可
            logger.exception("擷取執行緒結束時發生例外")
        executor.shutdown(wait=True)
        await engine.dispose()
        logger.info("FastAPI-NVR 已關閉")


def create_app() -> FastAPI:
    app = FastAPI(title="FastAPI-NVR", version="0.2.0", lifespan=lifespan)
    app.include_router(stream.router)
    app.include_router(recording.router)

    @app.get("/health", tags=["health"])
    async def health() -> dict:
        return {"status": "ok"}

    @app.get("/health/db", tags=["health"])
    async def health_db() -> dict:
        """檢查資料庫連線（Phase 2 schema 驗證用）。"""
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ok", "database": "reachable"}

    return app


app = create_app()
