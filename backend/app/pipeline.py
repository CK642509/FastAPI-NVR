"""VideoPipeline：核心協調者（對應 docs/ooa.md Phase 1→2）。

Phase 2 起，擷取迴圈持續從 FrameSource 讀幀並**分流**給兩個消費者：
  1. MJPEGStreamer — 每幀 JPEG 編碼後推送給串流 client；
  2. VideoWriter   — 分段寫入 mp4（錄影可由 API 動態開關）。

cv2 擷取、JPEG 編碼與 PyAV 編碼皆為同步阻塞操作，因此 start()（內部跑
_capture_loop()）設計為在背景執行緒中執行（見 server.py 的 ThreadPoolExecutor），
不阻塞 asyncio event loop。錄影開關（start/stop_recording）為 thread-safe 旗標。
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2

from .camera import Camera
from .sources import FrameSource
from .streaming import MJPEGStreamer
from .video_writer import VideoWriter

logger = logging.getLogger(__name__)


class VideoPipeline:
    def __init__(
        self,
        camera: Camera,
        source: FrameSource,
        streamer: MJPEGStreamer,
        recordings_dir: Path,
        segment_seconds: int,
        fallback_fps: float,
        jpeg_quality: int = 80,
        realtime_pacing: bool = False,
        record_on_start: bool = False,
    ) -> None:
        self._camera = camera
        self._source = source
        self._streamer = streamer
        self._recordings_dir = Path(recordings_dir)
        self._segment_seconds = max(1, segment_seconds)
        self._fallback_fps = fallback_fps
        self._jpeg_quality = jpeg_quality
        # synthetic / 影片檔來源讀取不受真實時間限制，需自行節流到接近即時
        self._realtime_pacing = realtime_pacing

        self._running = False
        # 錄影開關旗標；由 API 執行緒設定、擷取執行緒讀取
        self._recording = threading.Event()
        if record_on_start:
            self._recording.set()
        self._camera.is_recording = record_on_start

        self._fps = fallback_fps
        self._writer: Optional[VideoWriter] = None

    @property
    def camera(self) -> Camera:
        return self._camera

    @property
    def streamer(self) -> MJPEGStreamer:
        return self._streamer

    # ── 生命週期 ──────────────────────────────────────────────────────
    def start(self) -> None:
        """阻塞式執行擷取迴圈，直到 stop() 被呼叫或來源結束。"""
        self._running = True
        self._source.open()
        self._fps = max(1.0, self._source.fps or self._fallback_fps)
        logger.info(
            "Pipeline 啟動: camera=%s fps=%.2f 段長=%ds 錄影=%s",
            self._camera.name, self._fps, self._segment_seconds, self.is_recording,
        )
        try:
            self._capture_loop()
        finally:
            self._close_writer()
            self._source.release()
            self._camera.is_recording = False
            logger.info("Pipeline 已停止: camera=%s", self._camera.name)

    def stop(self) -> None:
        self._running = False

    # ── 錄影控制（thread-safe，供 API 呼叫）────────────────────────────
    def start_recording(self) -> None:
        self._recording.set()
        self._camera.is_recording = True
        logger.info("錄影開啟: camera=%s", self._camera.name)

    def stop_recording(self) -> None:
        self._recording.clear()
        self._camera.is_recording = False
        logger.info("錄影關閉: camera=%s", self._camera.name)

    @property
    def is_recording(self) -> bool:
        return self._recording.is_set()

    def recording_status(self) -> dict:
        return {
            "camera_id": self._camera.id,
            "is_recording": self.is_recording,
            "current_segment": self._writer.output_path if self._writer else None,
        }

    # ── 內部 ──────────────────────────────────────────────────────────
    def _segment_path(self) -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        return str(self._recordings_dir / f"{self._camera.name}_{ts}.mp4")

    def _close_writer(self) -> None:
        if self._writer is not None:
            self._writer.close()
            self._writer = None

    def _capture_loop(self) -> None:
        width: Optional[int] = None
        height: Optional[int] = None
        segment_frames = max(1, int(round(self._fps * self._segment_seconds)))
        frame_in_segment = 0
        encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), self._jpeg_quality]

        frame_interval = 1.0 / self._fps
        next_tick = time.monotonic()

        while self._running:
            frame = self._source.read()
            if frame is None:
                # Phase 2 仍不含重連（屬 Phase 4）；來源結束/中斷即收尾離開。
                logger.warning("來源讀取結束或失敗，停止擷取")
                break

            if width is None:
                height, width = frame.shape[:2]

            # ① 串流分支：JPEG 編碼後推給 MJPEGStreamer
            ok, buf = cv2.imencode(".jpg", frame, encode_params)
            if ok:
                self._streamer.push_frame(buf.tobytes())

            # ② 錄影分支：依錄影旗標寫入並處理分段
            if self._recording.is_set():
                if self._writer is None or frame_in_segment >= segment_frames:
                    self._close_writer()
                    self._writer = VideoWriter(width, height, self._fps)
                    self._writer.open(self._segment_path())
                    frame_in_segment = 0
                self._writer.write(frame)
                frame_in_segment += 1
            elif self._writer is not None:
                # 剛被關閉錄影 → 收尾目前這一段
                self._close_writer()
                frame_in_segment = 0

            if self._realtime_pacing:
                next_tick += frame_interval
                sleep = next_tick - time.monotonic()
                if sleep > 0:
                    time.sleep(sleep)
                else:
                    next_tick = time.monotonic()
