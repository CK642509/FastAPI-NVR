"""MJPEGStreamer：把擷取執行緒產生的 JPEG 幀，廣播給多個 HTTP 串流 client。

對應 docs/ooa.md Phase 2 的 MJPEGStreamer（push_frame / generate）。
擷取迴圈在背景執行緒呼叫 push_frame()，透過 loop.call_soon_threadsafe 安全地交給
asyncio event loop；每個 generate()（一個 HTTP 連線）擁有自己的 maxsize=1 佇列，
落後就丟舊幀，避免慢速 client 拖累整體。
"""

from __future__ import annotations

import asyncio
import logging
from typing import AsyncGenerator, Optional

logger = logging.getLogger(__name__)

# multipart/x-mixed-replace 的分界字串
_BOUNDARY = "frame"


class MJPEGStreamer:
    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        self._subscribers: set[asyncio.Queue[bytes]] = set()
        self._latest: Optional[bytes] = None

    @property
    def boundary(self) -> str:
        return _BOUNDARY

    @property
    def latest(self) -> Optional[bytes]:
        """最近一張 JPEG 幀（供 snapshot 使用）；尚無幀時為 None。"""
        return self._latest

    def push_frame(self, frame: bytes) -> None:
        """由擷取執行緒呼叫（thread-safe）：把 JPEG bytes 排進 event loop。"""
        self._loop.call_soon_threadsafe(self._dispatch, frame)

    def _dispatch(self, frame: bytes) -> None:
        # 於 event loop 執行緒內執行
        self._latest = frame
        for queue in self._subscribers:
            if queue.full():
                try:
                    queue.get_nowait()  # 丟掉最舊的一張，保留最新
                except asyncio.QueueEmpty:
                    pass
            queue.put_nowait(frame)

    async def generate(self) -> AsyncGenerator[bytes, None]:
        """產生 multipart MJPEG 串流；每個 HTTP 連線呼叫一次。"""
        queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=1)
        self._subscribers.add(queue)
        try:
            if self._latest is not None:
                yield self._multipart(self._latest)
            while True:
                frame = await queue.get()
                yield self._multipart(frame)
        finally:
            self._subscribers.discard(queue)

    @staticmethod
    def _multipart(frame: bytes) -> bytes:
        return (
            b"--" + _BOUNDARY.encode() + b"\r\n"
            b"Content-Type: image/jpeg\r\n"
            b"Content-Length: " + str(len(frame)).encode() + b"\r\n\r\n"
            + frame + b"\r\n"
        )
