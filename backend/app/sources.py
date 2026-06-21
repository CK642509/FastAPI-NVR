"""影像來源（FrameSource）。

`VideoPipeline._capture_loop()` 的擷取細節抽出於此，讓 webcam / RTSP / 影片檔 /
合成影像共用同一介面。cv2.VideoCapture 本身即可吃 webcam 索引(int)、RTSP URL 與
影片檔路徑；合成來源則純以 numpy 產生畫面，方便在無實體攝影機時驗證錄影管線。

讀取為同步阻塞操作，由 VideoPipeline 在獨立執行緒中呼叫（見 main.py）。
"""

from __future__ import annotations

import logging
from typing import Optional, Protocol, runtime_checkable

import cv2
import numpy as np

logger = logging.getLogger(__name__)


@runtime_checkable
class FrameSource(Protocol):
    """影像來源介面：開啟、逐幀讀取（BGR ndarray）、釋放。"""

    fps: float
    width: int
    height: int

    def open(self) -> None: ...
    def read(self) -> Optional[np.ndarray]: ...
    def release(self) -> None: ...


class OpenCVSource:
    """webcam / RTSP / 影片檔來源，皆透過 cv2.VideoCapture 擷取。"""

    def __init__(self, url: str, fallback_fps: float, loop: bool = False) -> None:
        self._raw = url
        self._loop = loop
        self._fallback_fps = fallback_fps
        self._cap: Optional[cv2.VideoCapture] = None
        self.fps = fallback_fps
        self.width = 0
        self.height = 0

    @staticmethod
    def _resolve(url: str):
        # 純數字字串 → 視為 webcam 索引
        if url.isdigit():
            return int(url)
        return url

    def open(self) -> None:
        source = self._resolve(self._raw)
        cap = cv2.VideoCapture(source)
        if not cap.isOpened():
            hint = ""
            if isinstance(source, int):
                # webcam 索引：容器內通常拿不到（Docker Desktop 無法 USB 直通；
                # Linux 需 compose 加 device 直通）。見 backend/README.md。
                hint = "（webcam 索引：容器內通常無法存取 USB 攝影機，詳見 README）"
            raise RuntimeError(f"無法開啟影像來源 {self._raw!r}{hint}")
        self._cap = cap

        src_fps = cap.get(cv2.CAP_PROP_FPS)
        self.fps = src_fps if src_fps and src_fps > 0 else self._fallback_fps
        self.width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 0
        self.height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 0
        logger.info(
            "已開啟影像來源 %r (fps=%.2f, %dx%d, loop=%s)",
            self._raw, self.fps, self.width, self.height, self._loop,
        )

    def read(self) -> Optional[np.ndarray]:
        if self._cap is None:
            raise RuntimeError("來源尚未 open()")
        ok, frame = self._cap.read()
        if not ok:
            # 影片檔播放完畢且設定循環 → 倒回開頭再讀一次
            if self._loop:
                self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ok, frame = self._cap.read()
                if ok:
                    return frame
            return None
        return frame

    def release(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None


class SyntheticSource:
    """合成影像來源：產生一個來回移動的方塊 + 幀編號。

    讓開發/驗證不需實體攝影機或影片檔即可跑通整條錄影管線。
    """

    def __init__(self, width: int, height: int, fps: float) -> None:
        self.width = width
        self.height = height
        self.fps = fps
        self._i = 0

    def open(self) -> None:
        logger.info(
            "使用合成影像來源 (%dx%d, fps=%.2f)", self.width, self.height, self.fps
        )

    def read(self) -> Optional[np.ndarray]:
        frame = np.full((self.height, self.width, 3), 30, dtype=np.uint8)

        box = 60
        period = max(self.width - box, 1)
        x = self._i % (2 * period)
        if x >= period:  # 形成來回往返
            x = 2 * period - x
        y = (self.height - box) // 2
        cv2.rectangle(frame, (x, y), (x + box, y + box), (0, 165, 255), -1)
        cv2.putText(
            frame, f"frame {self._i}", (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2,
        )

        self._i += 1
        return frame

    def release(self) -> None:
        pass


def create_source(
    url: str,
    fallback_fps: float,
    loop: bool,
    width: int,
    height: int,
) -> FrameSource:
    """依 camera_url 建立對應的影像來源。"""
    if url == "synthetic":
        return SyntheticSource(width, height, fallback_fps)
    return OpenCVSource(url, fallback_fps=fallback_fps, loop=loop)
