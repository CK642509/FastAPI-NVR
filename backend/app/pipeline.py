"""VideoPipeline：核心協調者（對應 docs/ooa.md Phase 1）。

持續從 FrameSource 擷取影像幀，並透過 VideoWriter 分段寫入 mp4。
cv2 擷取與 PyAV 編碼皆為同步阻塞操作，因此 start()（內部跑 _capture_loop()）
設計為在獨立執行緒中執行（見 main.py 的 ThreadPoolExecutor），不阻塞 asyncio
event loop。
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from .camera import Camera
from .sources import FrameSource
from .video_writer import VideoWriter

logger = logging.getLogger(__name__)


class VideoPipeline:
    def __init__(
        self,
        camera: Camera,
        source: FrameSource,
        recordings_dir: Path,
        segment_seconds: int,
        fallback_fps: float,
        realtime_pacing: bool = False,
    ) -> None:
        self._camera = camera
        self._source = source
        self._recordings_dir = Path(recordings_dir)
        self._segment_seconds = max(1, segment_seconds)
        self._fallback_fps = fallback_fps
        # synthetic / 影片檔來源讀取不受真實時間限制，需自行節流到接近即時
        self._realtime_pacing = realtime_pacing

        self._running = False
        self._fps = fallback_fps
        self._writer: Optional[VideoWriter] = None

    # ── 對外控制 ──────────────────────────────────────────────────────
    def start(self) -> None:
        """阻塞式執行擷取迴圈，直到 stop() 被呼叫或來源結束。"""
        self._running = True
        self._camera.is_recording = True
        self._source.open()
        self._fps = max(1.0, self._source.fps or self._fallback_fps)
        logger.info(
            "Pipeline 啟動: camera=%s fps=%.2f 段長=%ds",
            self._camera.name, self._fps, self._segment_seconds,
        )
        try:
            self._capture_loop()
        finally:
            if self._writer is not None:
                self._writer.close()
                self._writer = None
            self._source.release()
            self._camera.is_recording = False
            logger.info("Pipeline 已停止: camera=%s", self._camera.name)

    def stop(self) -> None:
        self._running = False

    # ── 內部 ──────────────────────────────────────────────────────────
    def _segment_path(self) -> str:
        # 毫秒精度的時間戳，避免短段檔名碰撞
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        return str(self._recordings_dir / f"{self._camera.name}_{ts}.mp4")

    def _capture_loop(self) -> None:
        width: Optional[int] = None
        height: Optional[int] = None
        segment_frames = max(1, int(round(self._fps * self._segment_seconds)))
        frame_in_segment = 0

        frame_interval = 1.0 / self._fps
        next_tick = time.monotonic()

        while self._running:
            frame = self._source.read()
            if frame is None:
                # Phase 1 不含重連（屬 Phase 4）；來源結束/中斷即收尾離開。
                logger.warning("來源讀取結束或失敗，停止擷取")
                break

            if width is None:
                height, width = frame.shape[:2]

            # 需要開新錄影段：首幀，或目前段已滿
            if self._writer is None or frame_in_segment >= segment_frames:
                if self._writer is not None:
                    self._writer.close()
                self._writer = VideoWriter(width, height, self._fps)
                self._writer.open(self._segment_path())
                frame_in_segment = 0

            self._writer.write(frame)
            frame_in_segment += 1

            if self._realtime_pacing:
                next_tick += frame_interval
                sleep = next_tick - time.monotonic()
                if sleep > 0:
                    time.sleep(sleep)
                else:
                    # 落後了就重置節拍，避免追幀爆衝
                    next_tick = time.monotonic()
