# FastAPI-NVR 後端 — Phase 1（核心錄影管線）

Phase 1 是一個**純後端**的影像擷取與持續分段錄影程式：從影像來源（webcam / RTSP /
影片檔 / 合成影像）逐幀讀取，以 PyAV 編碼成 H.264，分段儲存為 `.mp4`。

> 本階段**無前端、無串流、無 HTTP API**（這些在 Phase 2 加入）。設計對應
> `../docs/ooa.md` 的 Phase 1 類別圖：`Camera` / `VideoPipeline` / `VideoWriter`。

---

## 需求

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)（套件管理）

相依套件（由 `pyproject.toml` / `uv.lock` 管理）：`av`(PyAV)、`opencv-python-headless`、
`numpy`、`pydantic`、`pydantic-settings`。

---

## 安裝

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
| `CAMERA_NAME` | `cam1` | 攝影機名稱，會用於輸出檔名前綴 |
| `CAMERA_URL` | `synthetic` | 影像來源，見下表 |
| `CAMERA_LOOP` | `true` | 影片檔播放完畢是否從頭循環（只影響檔案來源） |
| `RECORDINGS_DIR` | `recordings` | 錄影輸出目錄 |
| `SEGMENT_SECONDS` | `60` | 每段 mp4 的長度（秒） |
| `TARGET_FPS` | `20` | 無法從來源取得 fps 時的後備值；synthetic 也用此值 |
| `FRAME_WIDTH` | `640` | 合成來源畫面寬（僅 `synthetic` 生效） |
| `FRAME_HEIGHT` | `480` | 合成來源畫面高（僅 `synthetic` 生效） |
| `LOG_LEVEL` | `INFO` | 日誌等級 |

### `CAMERA_URL` 支援的來源

| 寫法 | 對應來源 |
|---|---|
| `0`（純數字） | 本機 webcam 索引 |
| `rtsp://...` | RTSP 串流 |
| `C:\path\to\video.mp4` | 本機影片檔（可搭配 `CAMERA_LOOP` 循環） |
| `synthetic` | 內建合成影像（**免攝影機**即可測試整條管線） |

---

## 執行

```powershell
uv run python -m app.main
```

或用便捷進入點：

```powershell
uv run python main.py
```

按 **Ctrl+C** 即可優雅停止——程式會關閉目前的錄影段（沖洗編碼器並寫好檔尾）後再結束。

執行時的日誌會顯示每一段的開始與關閉，例如：

```
INFO [nvr] NVR Phase 1 啟動：來源=synthetic 段長=60s 輸出目錄=recordings
INFO [app.pipeline] Pipeline 啟動: camera=cam1 fps=20.00 段長=60s
INFO [app.video_writer] 開始錄影段: recordings\cam1_20260621_122154_795.mp4
INFO [app.video_writer] 關閉錄影段: recordings\cam1_20260621_122154_795.mp4 (1200 幀)
```

---

## 輸出與分段行為

- 檔名格式：`{CAMERA_NAME}_{YYYYmmdd_HHMMSS_mmm}.mp4`（毫秒精度避免碰撞）。
- 每段長度以**幀數**為界（`round(fps × SEGMENT_SECONDS)`），確保每段時長精確，不受
  擷取速度波動影響。
- 編碼：H.264（`yuv420p`，`crf=23`、`preset=veryfast`），輸出 `.mp4`。
- 來源節流：`synthetic` 與影片檔來源會自行節流到接近即時；webcam / RTSP 由硬體或網路
  自然限速。
- Phase 1 **不含**來源中斷自動重連（屬 Phase 4）；來源結束或讀取失敗即收尾離開。

---

## 測試 / 驗證

不需任何攝影機，用預設的合成來源跑一小段即可驗證整條管線。建議用較短的段長與較低的
fps 快速產出多個檔案：

```powershell
# PowerShell：用環境變數覆寫，輸出到暫存目錄
$env:CAMERA_URL="synthetic"; $env:SEGMENT_SECONDS="2"; $env:TARGET_FPS="10"; `
$env:RECORDINGS_DIR="recordings_test"
uv run python -m app.main
# 跑幾秒後按 Ctrl+C 停止
```

驗證重點：

1. `recordings_test/` 下出現多個 `.mp4`，每個完整段約 `SEGMENT_SECONDS × TARGET_FPS` 幀。
2. 用 PyAV 重新開檔解碼，確認檔案有效且可讀：

   ```powershell
   uv run python -c "import av,glob; f=sorted(glob.glob('recordings_test/*.mp4'))[0]; c=av.open(f); s=c.streams.video[0]; print(f, s.codec_context.name, f'{s.width}x{s.height}', sum(1 for _ in c.decode(video=0)),'frames')"
   ```

   或用任意播放器（VLC 等）直接開啟確認畫面為來回移動的方塊 + 幀編號。

> 若要用**影片檔**測試，把 `CAMERA_URL` 指到一個 `.mp4`，並保持 `CAMERA_LOOP=true`，
> 即可在無攝影機的情況下產生連續輸入。

---

## 程式結構

```
backend/
├─ app/
│  ├─ config.py        # Pydantic Settings（讀 .env）
│  ├─ camera.py        # Camera 資料模型
│  ├─ sources.py       # FrameSource / OpenCVSource / SyntheticSource
│  ├─ video_writer.py  # VideoWriter（PyAV → H.264 mp4）
│  ├─ pipeline.py      # VideoPipeline（擷取迴圈 + 分段）
│  └─ main.py          # asyncio 進入點（擷取跑在 ThreadPoolExecutor）
├─ main.py             # 便捷進入點（= python -m app.main）
├─ Dockerfile
├─ pyproject.toml / uv.lock
└─ .env.example
```

cv2 擷取與 PyAV 編碼皆為**同步阻塞**操作，因此擷取迴圈跑在 `ThreadPoolExecutor` 執行緒中，
由 asyncio 主執行緒等待其結束並處理停止訊號（SIGINT / SIGTERM）。

---

## Docker

後端映像由 `./backend` 建置（compose 服務 `api-server`）。容器內錄影預設輸出到
`/app/recordings`，對應 host 的 `storage/recordings`：

```powershell
# 於專案根目錄（FastAPI-NVR/）
docker compose up --build api-server
```

> 注意：`docker compose up`（不指定服務）會一併啟動 `db`、`caddy`；Phase 1 本身用不到
> 它們。`api-server` 的環境變數由根目錄 `.env`（compose `env_file`）注入。
