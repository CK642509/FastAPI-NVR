"""Camera 資料模型（對應 docs/ooa.md Phase 1）。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Camera:
    """單一影像來源的描述。

    Phase 1 僅在記憶體中存在（由 `.env` 設定產生）；Phase 4 之後才有
    對應的資料庫設定（CameraConfig）與 CRUD。
    """

    id: int
    name: str
    url: str
    is_recording: bool = False
