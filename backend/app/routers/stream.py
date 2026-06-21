"""StreamRouter（對應 docs/ooa.md Phase 2）：MJPEG 串流與單張快照。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from ..pipeline import VideoPipeline
from .deps import get_pipeline

router = APIRouter(prefix="/api/cameras", tags=["stream"])


@router.get("/{camera_id}/stream")
async def stream(camera_id: int, request: Request) -> StreamingResponse:
    """MJPEG 即時串流（multipart/x-mixed-replace）。"""
    pipeline: VideoPipeline = get_pipeline(request, camera_id)
    streamer = pipeline.streamer
    return StreamingResponse(
        streamer.generate(),
        media_type=f"multipart/x-mixed-replace; boundary={streamer.boundary}",
        headers={"Cache-Control": "no-cache", "Connection": "close"},
    )


@router.get("/{camera_id}/snapshot")
async def snapshot(camera_id: int, request: Request) -> Response:
    """最近一張畫面的 JPEG 快照。"""
    pipeline: VideoPipeline = get_pipeline(request, camera_id)
    frame = pipeline.streamer.latest
    if frame is None:
        raise HTTPException(status_code=503, detail="尚無可用畫面")
    return Response(content=frame, media_type="image/jpeg")
