"""應用程式設定（Pydantic v2 Settings）。

所有設定皆可透過環境變數或 `.env` 覆寫（見 `.env.example`）。
Phase 2 起以 FastAPI 提供 MJPEG 串流與錄影控制 API；攝影機仍由 `.env` 設定
（前端設定為 Phase 4）。資料庫 schema 為 Phase 3 事件功能預備。
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── 攝影機 / 影像來源 ──────────────────────────────────────────────
    camera_name: str = "cam1"
    # 影像來源，支援四種寫法：
    #   - 數字字串，例如 "0"  → 本機 webcam 索引
    #   - "rtsp://..."        → RTSP 串流
    #   - 影片檔路徑           → 檔案來源（可循環播放，方便測試）
    #   - "synthetic"         → 內建合成影像（免實體攝影機即可驗證錄影管線）
    camera_url: str = "synthetic"
    # 檔案來源播放結束後是否從頭循環（webcam/RTSP/synthetic 不受影響）
    camera_loop: bool = True

    # ── 錄影 ──────────────────────────────────────────────────────────
    recordings_dir: Path = Path("recordings")
    segment_seconds: int = 60  # 每段 mp4 的長度（秒）
    # 無法從來源取得 fps 時的後備值；synthetic 來源也採用此 fps
    target_fps: float = 20.0

    # 啟動時是否立即開始錄影；Phase 2 起錄影可由 API 開關
    record_on_start: bool = False

    # ── 合成來源畫面尺寸（僅 camera_url="synthetic" 時生效）──────────────
    frame_width: int = 640
    frame_height: int = 480

    # ── 串流（MJPEG）──────────────────────────────────────────────────
    jpeg_quality: int = 80  # 1-100，串流/快照的 JPEG 品質

    # ── HTTP 伺服器 ───────────────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 8000

    # ── 資料庫 ────────────────────────────────────────────────────────
    # SQLAlchemy async 連線字串；容器內由 compose 注入指向 db 服務。
    database_url: str = (
        "postgresql+asyncpg://nvr:nvr@localhost:5432/nvr_db"
    )

    log_level: str = "INFO"


settings = Settings()
