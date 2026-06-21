"""VideoWriter：封裝 PyAV 的開檔、寫幀、關檔，輸出 H.264 mp4（對應 docs/ooa.md）。

接收 OpenCV 的 BGR ndarray 幀，編碼為 H.264 寫入單一 mp4 檔。分段邏輯由
VideoPipeline 控制：每段呼叫一次 open()/close()。
"""

from __future__ import annotations

import logging
from fractions import Fraction
from pathlib import Path
from typing import Optional

import av
import numpy as np

logger = logging.getLogger(__name__)


class VideoWriter:
    def __init__(self, width: int, height: int, fps: float) -> None:
        self._width = width
        self._height = height
        # H.264 / mp4 的 timebase 以整數 fps 表示最穩定
        self._fps = max(1, int(round(fps)))
        self._container: Optional[av.container.OutputContainer] = None
        self._stream = None
        self._frame_count = 0
        self.output_path: Optional[str] = None

    def open(self, path: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        container = av.open(path, mode="w")
        stream = container.add_stream("h264", rate=self._fps)
        stream.width = self._width
        stream.height = self._height
        stream.pix_fmt = "yuv420p"
        stream.options = {"crf": "23", "preset": "veryfast"}

        self._container = container
        self._stream = stream
        self._frame_count = 0
        self.output_path = path
        logger.info("開始錄影段: %s", path)

    def write(self, frame: np.ndarray) -> None:
        if self._container is None or self._stream is None:
            raise RuntimeError("VideoWriter 尚未 open()")

        video_frame = av.VideoFrame.from_ndarray(frame, format="bgr24")
        video_frame.pts = self._frame_count
        video_frame.time_base = Fraction(1, self._fps)

        for packet in self._stream.encode(video_frame):
            self._container.mux(packet)
        self._frame_count += 1

    def close(self) -> None:
        if self._container is None:
            return
        try:
            # 沖洗編碼器內剩餘的幀
            for packet in self._stream.encode():
                self._container.mux(packet)
        finally:
            self._container.close()
            logger.info(
                "關閉錄影段: %s (%d 幀)", self.output_path, self._frame_count
            )
            self._container = None
            self._stream = None
