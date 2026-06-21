"""Phase 1 進入點：純 asyncio 應用程式（無前端、無 API）。

依 `.env` 設定建立 Camera 與影像來源，於 ThreadPoolExecutor 執行緒中跑同步的
擷取/錄影迴圈，主執行緒以 asyncio 等待其結束並處理停止訊號（Ctrl+C / SIGTERM）。
"""

from __future__ import annotations

import asyncio
import logging
import signal
from concurrent.futures import ThreadPoolExecutor

from .camera import Camera
from .config import settings
from .pipeline import VideoPipeline
from .sources import create_source

logger = logging.getLogger("nvr")


def _configure_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


def _is_realtime_source(url: str) -> bool:
    """synthetic 與本機影片檔的讀取不受真實時間限制，需節流到接近即時。

    webcam(索引) 與 RTSP 由硬體/網路自然限速，不需額外節流。
    """
    if url == "synthetic":
        return True
    if url.isdigit():  # webcam 索引
        return False
    if url.startswith(("rtsp://", "rtsps://", "http://", "https://")):
        return False
    return True  # 其餘視為本機影片檔


async def run() -> None:
    _configure_logging()

    camera = Camera(id=1, name=settings.camera_name, url=settings.camera_url)
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
        recordings_dir=settings.recordings_dir,
        segment_seconds=settings.segment_seconds,
        fallback_fps=settings.target_fps,
        realtime_pacing=_is_realtime_source(settings.camera_url),
    )

    loop = asyncio.get_running_loop()

    def _request_stop() -> None:
        logger.info("收到停止訊號，正在關閉…")
        pipeline.stop()

    # POSIX 可用 loop signal handler；Windows 退回 signal.signal。
    registered = False
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_stop)
            registered = True
        except (NotImplementedError, AttributeError):
            pass
    if not registered:
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, lambda *_: _request_stop())
            except (ValueError, OSError):
                pass

    logger.info(
        "NVR Phase 1 啟動：來源=%s 段長=%ds 輸出目錄=%s",
        settings.camera_url, settings.segment_seconds, settings.recordings_dir,
    )

    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="capture")
    capture_future = loop.run_in_executor(executor, pipeline.start)

    # 定期讓出控制權，使（Windows 上的）signal handler 有機會執行並停止 pipeline。
    while not capture_future.done():
        await asyncio.sleep(0.2)

    try:
        await capture_future  # 重新拋出擷取執行緒內的例外（若有）
    finally:
        executor.shutdown(wait=True)


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
