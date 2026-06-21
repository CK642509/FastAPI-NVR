# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

**Phase 1 (Core — capture + segmented recording) is implemented.** Phases 2–5 are not yet
started; `caddy/Caddyfile` is still an empty placeholder. The authoritative spec for what to
build lives in `docs/`:

- `docs/proposal.md` — the proposal: tech stack table, system architecture diagram, and the
  dated Phase 1–5 timeline.
- `docs/milestone.md` — feature breakdown per phase.
- `docs/ooa.md` — incremental OOA/OOD class diagrams (Mermaid) per phase, plus the cumulative
  full-system class diagram. **This is the design contract**: class names, responsibilities, and
  relationships defined here are what the implementation should follow.

When implementing a feature, find its phase in `docs/ooa.md` first — the class structure,
abstract base classes, and design patterns are already specified there.

### Backend (Phase 1)

The backend is a **pure-asyncio app** (no FastAPI/API yet — that arrives in Phase 2). Code lives
in `backend/app/`, following the Phase 1 design contract (`Camera` / `VideoPipeline` /
`VideoWriter`):

- `app/config.py` — Pydantic v2 `Settings`, all config via `.env` (see `backend/.env.example`).
- `app/camera.py` — `Camera` dataclass.
- `app/sources.py` — `FrameSource` protocol + `OpenCVSource` (webcam / RTSP / video file, via
  `cv2.VideoCapture`) + `SyntheticSource` (generated frames, for testing without a camera).
- `app/video_writer.py` — `VideoWriter`, PyAV → H.264 mp4.
- `app/pipeline.py` — `VideoPipeline`, capture loop + segmentation (segment boundary by frame
  count = `fps × segment_seconds`).
- `app/main.py` — asyncio entry point; the blocking capture loop runs in a `ThreadPoolExecutor`
  (cv2/PyAV are synchronous), with SIGINT/SIGTERM graceful shutdown.

Dependencies are managed with **uv** (`pyproject.toml` + `uv.lock`). `CAMERA_URL` selects the
source: a digit (`0`) = webcam index, `rtsp://…` = RTSP, a path = video file (loops if
`CAMERA_LOOP`), `synthetic` = generated frames. Recordings default to `recordings/` (→ container
`/app/recordings` → host `storage/recordings`).

Run Phase 1 locally:
```powershell
cd backend
copy .env.example .env   # defaults to CAMERA_URL=synthetic (no camera needed)
uv run python -m app.main # Ctrl+C to stop
```

## Repository layout

- `backend/` — FastAPI application (Docker-built service `api-server`, container `nvr-core`).
- `caddy/Caddyfile` — Caddy reverse-proxy + static file + `/media/*` video config.
- `web` — **git submodule** (the Vue 3 + TypeScript frontend, repo
  [FastAPI-NVR-Web](https://github.com/CK642509/FastAPI-NVR-Web), tracks the `build` branch).
- `docker-compose.yaml` — orchestrates `caddy` (gateway) + `api-server` + `db` (Postgres 15).
- `docs/` — design documents (see above).

## Common commands

Clone with submodule (required — the frontend is a submodule):
```
git clone <repository-url> --recursive
```

Update the frontend to its latest built version:
```
git submodule update --remote web
```

Run the full stack (requires a `.env` file — see below):
```
docker compose up --build
```

The backend image is built from `./backend`; `web`'s built `dist/` and `storage/recordings`
are mounted into Caddy as static/media volumes.

## Environment

`docker-compose.yaml` reads from a `.env` file (gitignored). Required variables:
`DB_USER`, `DB_PASSWORD` (the Postgres database name is hardcoded as `nvr_db`). The
`api-server` service loads the same `.env` via `env_file`.

## Architecture (target design)

The runtime centers on a per-camera **`VideoPipeline`** that captures frames and fans them out to
three consumers: `MJPEGStreamer` (live streaming), `VideoWriter` (PyAV recording), and a
`FrameAnalyzer` (analysis). Because OpenCV (`cv2`) capture is synchronous, it runs inside a
`ThreadPoolExecutor`, bridged to the asyncio app.

Key extension points the design depends on — preserve these when implementing:

- **`FrameAnalyzer` (abstract, Template Method)** — `MotionDetector` (Phase 3, OpenCV MOG2) and
  `AIAnalyzer` (Phase 5, YOLO) both subclass it. `EventService` consumes `AnalysisResult` and does
  not care which analyzer produced it.
- **`NotificationStrategy` (abstract, Strategy Pattern)** — `TelegramNotifier`, `DiscordNotifier`.
  Adding a notification channel means adding one class, not touching `EventService`.
- **`EventService` (Facade)** — coordinates event creation, `EventRecorder` (pre/post-event ring
  buffer clipping), notifications, and `WebSocketManager` broadcast to the frontend.
- **Repository Pattern** — `CameraRepository` / `EventRepository` isolate SQLAlchemy data access.
- **`CameraManager` (Facade, Phase 5)** — owns the lifecycle of multiple `VideoPipeline`s and their
  `ReconnectionManager`s.

Request flow: browser → Caddy (`:80`/`:443`) → Vue frontend (static) or FastAPI; Caddy also serves
recorded video directly from `/media/*` for performance. FastAPI can push config changes into a
running `VideoPipeline` dynamically.

## Known caveats

- `docker-compose.yaml` mounts the frontend from `./web-submodule/dist`, but the submodule is
  actually at `web` (per `.gitmodules`). Verify/reconcile this path before relying on the Caddy
  static mount.
