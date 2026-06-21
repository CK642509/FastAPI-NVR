"""路由共用依賴：依 camera_id 取得執行中的 VideoPipeline。

Phase 2 僅單一攝影機（id 由 `.env` 的攝影機產生，預設為 1）；多攝影機與
CameraManager 屬 Phase 5。`app.state.pipelines` 是 {camera_id: VideoPipeline}。
"""

from __future__ import annotations

from fastapi import HTTPException, Request

from ..pipeline import VideoPipeline


def get_pipeline(request: Request, camera_id: int) -> VideoPipeline:
    pipelines: dict[int, VideoPipeline] = getattr(request.app.state, "pipelines", {})
    pipeline = pipelines.get(camera_id)
    if pipeline is None:
        raise HTTPException(status_code=404, detail=f"camera {camera_id} 不存在")
    return pipeline
