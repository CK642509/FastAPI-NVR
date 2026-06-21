# FastAPI-NVR 後端

以 FastAPI 打造的輕量 NVR 後端：影像擷取、持續/可控分段錄影、MJPEG 即時串流。

## 階段進度

- **Phase 1（核心錄影管線）✅** — 影像擷取（webcam / RTSP / 影片檔 / 合成影像）→ PyAV
  編碼 H.264 → 分段 `.mp4`。
- **Phase 2 後端（MJPEG 串流 + 控制 API + DB schema）✅** — 擷取迴圈分流給「串流」與
  「錄影」兩個消費者；錄影可由 API 開關；建立 PostgreSQL schema（為 Phase 3 預備）。
  > Vue3 前端與全 compose 容器化是 Phase 2 後段（之後再做）。

設計對應 `../docs/ooa.md`：Phase 1 的 `Camera` / `VideoPipeline` / `VideoWriter`，
Phase 2 的 `MJPEGStreamer` / `StreamRouter` / `RecordingRouter`。

---

## 需求

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)（套件管理）
- Docker（跑 PostgreSQL；僅 DB schema/`/health/db` 需要）

主要相依：`fastapi`、`uvicorn`、`av`(PyAV)、`opencv-python-headless`、`numpy`、
`sqlalchemy[asyncio]`、`asyncpg`、`alembic`、`pydantic` / `pydantic-settings`。

```powershell
cd backend
uv sync          # 建立 .venv 並安裝相依
```

---

## 設定

所有設定透過環境變數或 `backend/.env` 提供。先從範例複製一份：

```powershell
copy .env.example .env
```

| 變數 | 預設 | 說明 |
|---|---|---|
| `CAMERA_NAME` | `cam1` | 攝影機名稱，用於輸出檔名前綴 |
| `CAMERA_URL` | `synthetic` | 影像來源，見下表 |
| `CAMERA_LOOP` | `true` | 影片檔播放完畢是否從頭循環（只影響檔案來源） |
| `RECORDINGS_DIR` | `recordings` | 錄影輸出目錄 |
| `SEGMENT_SECONDS` | `60` | 每段 mp4 的長度（秒） |
| `TARGET_FPS` | `20` | 無法從來源取得 fps 時的後備值；synthetic 也用此值 |
| `RECORD_ON_START` | `false` | 啟動時是否立即錄影（Phase 2 起錄影可由 API 開關） |
| `FRAME_WIDTH` / `FRAME_HEIGHT` | `640`/`480` | 合成來源畫面尺寸（僅 `synthetic` 生效） |
| `JPEG_QUALITY` | `80` | 串流/快照的 JPEG 品質（1–100） |
| `HOST` / `PORT` | `0.0.0.0`/`8000` | HTTP 伺服器位址 |
| `DATABASE_URL` | `postgresql+asyncpg://nvr:nvr@localhost:5432/nvr_db` | SQLAlchemy async 連線字串 |
| `LOG_LEVEL` | `INFO` | 日誌等級 |

### `CAMERA_URL` 支援的來源

| 寫法 | 對應來源 |
|---|---|
| `0`（純數字） | 本機 webcam 索引 |
| `rtsp://...` | RTSP 串流 |
| `C:\path\to\video.mp4` | 本機影片檔（可搭配 `CAMERA_LOOP` 循環） |
| `synthetic` | 內建合成影像（**免攝影機**即可測試整條管線） |

### ⚠️ Webcam 與容器

`CAMERA_URL=0`（USB webcam）**在容器中能否使用，取決於宿主 OS**：

- **Windows / macOS（Docker Desktop）**：容器跑在 Linux VM 內，**無法 USB 直通**——
  這不是權限設定問題，怎麼設都拿不到攝影機。請改用以下其一：
  - 開發 webcam 時**原生執行後端**（`uv run python -m app.main`），不要走容器；
  - 容器內改用 `rtsp://...` / 影片檔 / `synthetic` 來源。
- **Linux 主機**：容器**可以**存取 USB 攝影機，但需在 compose 為 `api-server` 開啟 device
  直通（預設已註解，見根目錄 `docker-compose.yaml`）：

  ```yaml
  devices:
    - /dev/video0:/dev/video0    # 換成實際裝置；查法 ls /dev/video*
  group_add:
    - video                      # 或填宿主 video 群組 GID：getent group video
  ```

來源開啟失敗（含容器內取不到 webcam）時，後端會記錄明確的 ERROR 日誌，App 仍持續運作
（API 可回應，只是無畫面、snapshot 回 503），方便排查。

---

## 資料庫 schema（Alembic migration）

Phase 2 僅建立 schema（`cameras` / `events` / `notification_config`），為 Phase 3 的事件/
通知功能預備；執行期的攝影機設定仍來自 `.env`，尚未使用這些資料表。

先起一個 PostgreSQL（用根目錄 compose 的 `db` 服務，需先有根目錄 `.env`，見下方 Docker），
再套用 migration：

```powershell
# 於專案根目錄起 DB（對外開 5432）
docker compose up -d db

# 於 backend/ 套用 migration
uv run alembic upgrade head     # 建表
uv run alembic downgrade base   # （需要時）還原
```

---

## 執行

```powershell
uv run python -m app.main        # = uvicorn app.server:app --host $HOST --port $PORT
# 或
uv run python main.py
```

啟動後：

- Swagger 文件：<http://localhost:8000/docs>
- 健康檢查：`GET /health`、`GET /health/db`（後者會實際連 DB）

按 **Ctrl+C** 優雅停止——會關閉目前錄影段並釋放來源。

---

## API 端點

> Phase 2 為單一攝影機，`camera_id` 固定為 `1`（由 `.env` 的攝影機產生）。

| 方法 | 路徑 | 說明 |
|---|---|---|
| `GET` | `/api/cameras/{id}/stream` | MJPEG 即時串流（`multipart/x-mixed-replace`） |
| `GET` | `/api/cameras/{id}/snapshot` | 最近一張畫面的 JPEG 快照 |
| `POST` | `/api/cameras/{id}/recording/start` | 開始錄影 |
| `POST` | `/api/cameras/{id}/recording/stop` | 停止錄影 |
| `GET` | `/api/cameras/{id}/recording/status` | 查詢錄影狀態 |
| `GET` | `/health`、`/health/db` | 健康檢查 |

範例：

```powershell
# 瀏覽器直接開 MJPEG 串流
start http://localhost:8000/api/cameras/1/stream

# 控制錄影
curl -X POST http://localhost:8000/api/cameras/1/recording/start
curl http://localhost:8000/api/cameras/1/recording/status
curl -X POST http://localhost:8000/api/cameras/1/recording/stop

# 抓一張快照
curl http://localhost:8000/api/cameras/1/snapshot -o snap.jpg
```

串流（擷取）在伺服器啟動時即持續運作；**錄影是獨立開關**，開關時串流不中斷。

---

## 輸出與分段行為

- 檔名格式：`{CAMERA_NAME}_{YYYYmmdd_HHMMSS_mmm}.mp4`（毫秒精度避免碰撞）。
- 每段長度以**幀數**為界（`round(fps × SEGMENT_SECONDS)`），確保每段時長精確。
- 編碼：H.264（`yuv420p`，`crf=23`、`preset=veryfast`），輸出 `.mp4`。
- 來源節流：`synthetic` 與影片檔來源自行節流到接近即時；webcam / RTSP 由硬體/網路自然限速。
- Phase 2 仍**不含**來源中斷自動重連（屬 Phase 4）；來源結束或讀取失敗即收尾離開。

---

## 測試 / 驗證

免攝影機，用預設合成來源即可端到端驗證。建議用較短段長 + 較低 fps：

```powershell
copy .env.example .env
# 編輯 .env：SEGMENT_SECONDS=2、TARGET_FPS=8（可選）
docker compose up -d db          # 於專案根目錄；/health/db 需要
cd backend; uv run alembic upgrade head
uv run python -m app.main
```

驗證重點：

1. `GET /health` → `{"status":"ok"}`；`GET /health/db` → `{"database":"reachable"}`。
2. `GET /api/cameras/1/snapshot` 回傳 JPEG（開頭 `FF D8`）。
3. `GET /api/cameras/1/stream` 回傳 `multipart/x-mixed-replace`，內含多個 `--frame` 邊界與
   JPEG（瀏覽器可直接看到來回移動的方塊 + 幀編號）。
4. `recording/start` 後 `RECORDINGS_DIR/` 開始產生 `.mp4`；`recording/stop` 後停止；可用
   PyAV 解碼確認：
   ```powershell
   uv run python -c "import av,glob; f=sorted(glob.glob('recordings/*.mp4'))[0]; c=av.open(f); s=c.streams.video[0]; print(f, s.codec_context.name, f'{s.width}x{s.height}', sum(1 for _ in c.decode(video=0)),'frames')"
   ```

---

## 程式結構

```
backend/
├─ app/
│  ├─ config.py        # Pydantic Settings（讀 .env）
│  ├─ camera.py        # Camera 資料模型（in-memory）
│  ├─ sources.py       # FrameSource / OpenCVSource / SyntheticSource
│  ├─ video_writer.py  # VideoWriter（PyAV → H.264 mp4）
│  ├─ streaming.py     # MJPEGStreamer（thread-safe，廣播給多個 client）
│  ├─ pipeline.py      # VideoPipeline（擷取迴圈 → 串流 + 可控錄影分流）
│  ├─ routers/         # StreamRouter / RecordingRouter + 共用依賴
│  ├─ db/              # SQLAlchemy async engine / Base / models
│  ├─ server.py        # FastAPI app + lifespan（背景啟動 pipeline）
│  └─ main.py          # 進入點（uvicorn）
├─ alembic/ alembic.ini  # DB migration
├─ main.py             # 便捷進入點（= python -m app.main）
├─ Dockerfile
├─ pyproject.toml / uv.lock
└─ .env.example
```

cv2 擷取、JPEG 編碼與 PyAV 編碼皆為**同步阻塞**操作，故擷取迴圈跑在 `ThreadPoolExecutor`
執行緒中，由 FastAPI lifespan 的 asyncio 主執行緒管理其啟停；串流幀透過
`loop.call_soon_threadsafe` 安全地交給 event loop 廣播。

---

## Docker（全 compose）

Phase 2 已完成全容器化：`docker compose up --build` 一次起 **Caddy + api-server + db**。需於
**專案根目錄**準備 `.env`（見根目錄 `.env.example`，含 `DB_USER` / `DB_PASSWORD` 與影像來源）。

```powershell
# 於專案根目錄（FastAPI-NVR/）
docker compose up --build              # Caddy(:80) + api-server + db 全部起來
# DB migration（首次或 schema 有變時，於容器內執行）
docker compose exec api-server alembic upgrade head
```

存取（全部經由 Caddy `:80` 同源）：

| URL | 內容 |
|---|---|
| `http://localhost/` | 前端（Vue SPA，由 `web` submodule 提供） |
| `http://localhost/api/...` | 反向代理到 api-server（含 MJPEG 串流） |
| `http://localhost/media/<file>.mp4` | Caddy 直讀錄影檔 |
| `http://localhost/health`、`/health/db` | 健康檢查 |

- 服務間：Caddy 反代到 `api-server:8000`；MJPEG 用 `flush_interval -1` 即時送出。
- 前端靜態檔由 `web` submodule（build 分支，產物在根目錄）掛載到 Caddy。
- 容器內錄影輸出 `/app/recordings` → host `storage/recordings`，Caddy 以 `/media/*` 直讀。
- `api-server` 的 `DATABASE_URL` 由 compose 以 `DB_USER`/`DB_PASSWORD` 組出，指向 `db`。
- 開發期 `api-server:8000`、`db:5432` 仍對 host 開放，方便直連 / 跑 alembic。

> 注意：`postgres:18` 映像的資料卷需掛在 `/var/lib/postgresql`（非 `.../data`），compose 已修正。
> `web` submodule 目前是**舊版**前端 build；要讓 Caddy 提供最新 Phase 2 UI，需先用
> `FastAPI-NVR-Web/scripts/build-image.ps1` 發佈到 build 分支，再 `git submodule update --remote web`。
