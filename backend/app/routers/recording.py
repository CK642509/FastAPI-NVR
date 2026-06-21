"""RecordingRouter（對應 docs/ooa.md Phase 2）：錄影開關與狀態查詢。"""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from ..pipeline import VideoPipeline
from .deps import get_pipeline

router = APIRouter(prefix="/api/cameras", tags=["recording"])


class RecordingStatus(BaseModel):
    camera_id: int
    is_recording: bool
    current_segment: str | None = None


@router.post("/{camera_id}/recording/start", response_model=RecordingStatus)
async def start(camera_id: int, request: Request) -> RecordingStatus:
    pipeline: VideoPipeline = get_pipeline(request, camera_id)
    pipeline.start_recording()
    return RecordingStatus(**pipeline.recording_status())


@router.post("/{camera_id}/recording/stop", response_model=RecordingStatus)
async def stop(camera_id: int, request: Request) -> RecordingStatus:
    pipeline: VideoPipeline = get_pipeline(request, camera_id)
    pipeline.stop_recording()
    return RecordingStatus(**pipeline.recording_status())


@router.get("/{camera_id}/recording/status", response_model=RecordingStatus)
async def status(camera_id: int, request: Request) -> RecordingStatus:
    pipeline: VideoPipeline = get_pipeline(request, camera_id)
    return RecordingStatus(**pipeline.recording_status())
