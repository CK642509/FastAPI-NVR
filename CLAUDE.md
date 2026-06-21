# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

**Phase 2 is complete** end-to-end: Phase 1 capture + segmented recording, the Phase 2 backend
(MJPEG streaming + control API + DB schema), the Phase 2 frontend (Vue 3 + Vuetify live view, in
the sibling `FastAPI-NVR-Web/` worktree), and the full compose/Caddy wiring (`caddy/Caddyfile` +
`docker-compose.yaml`). `docker compose up --build` brings up Caddy + api-server + db; Caddy
serves the frontend, proxies `/api` + `/health`, and serves `/media/*` recordings. Not yet done:
Phases 3–5, and the `web` submodule still points at an **older** frontend build — publish the
current UI with `FastAPI-NVR-Web/scripts/build-image.ps1` then `git submodule update --remote web`.
The authoritative spec for what to build lives in `docs/`:

- `docs/proposal.md` — the proposal: tech stack table, system architecture diagram, and the
  dated Phase 1–5 timeline.
- `docs/milestone.md` — feature breakdown per phase.
- `docs/ooa.md` — incremental OOA/OOD class diagrams (Mermaid) per phase, plus the cumulative
  full-system class diagram. **This is the design contract**: class names, responsibilities, and
  relationships defined here are what the implementation should follow.

When implementing a feature, find its phase in `docs/ooa.md` first — the class structure,
abstract base classes, and design patterns are already specified there.

### Backend

A **FastAPI app** (Phase 2). Code lives in `backend/app/`, following the `docs/ooa.md` design
contract. Dependencies are managed with **uv** (`pyproject.toml` + `uv.lock`); run details and
the full env-var table are in `backend/README.md`.

Capture / recording (Phase 1):
- `app/sources.py` — `FrameSource` protocol + `OpenCVSource` (webcam / RTSP / video file, via
  `cv2.VideoCapture`) + `SyntheticSource` (generated frames, for testing without a camera).
  `CAMERA_URL` selects: digit (`0`) = webcam, `rtsp://…` = RTSP, a path = video file (loops if
  `CAMERA_LOOP`), `synthetic` = generated.
- `app/video_writer.py` — `VideoWriter`, PyAV → H.264 mp4.
- `app/pipeline.py` — `VideoPipeline`. The capture loop **fans out** each frame to (a) the
  `MJPEGStreamer` (JPEG-encoded) and (b) the `VideoWriter` when recording is on. Recording is a
  thread-safe toggle (`start_recording`/`stop_recording`); segment boundary = `fps × segment_seconds`
  frames. The blocking loop runs in a `ThreadPoolExecutor` (cv2/PyAV are synchronous).

Streaming + API (Phase 2):
- `app/streaming.py` — `MJPEGStreamer`; capture thread pushes frames via
  `loop.call_soon_threadsafe`, each HTTP client gets a drop-old queue.
- `app/routers/` — `StreamRouter` (`/api/cameras/{id}/stream`, `/snapshot`) and `RecordingRouter`
  (`/recording/{start,stop,status}`). `app.state.pipelines` is `{camera_id: VideoPipeline}`
  (single camera, id `1`, in Phase 2).
- `app/server.py` — `create_app()` + `lifespan` that starts the pipeline in the background on
  startup and stops it on shutdown. `app/main.py` launches uvicorn.

Database (Phase 2 — **schema only**, for Phase 3):
- `app/db/` — SQLAlchemy 2.0 **async** engine/session + models (`cameras`, `events`,
  `notification_config`). Not yet used by runtime logic; the running camera still comes from `.env`.
- `alembic/` + `alembic.ini` — migrations. Apply with `uv run alembic upgrade head` (needs the
  `db` service up). Note: `alembic.ini` must stay ASCII (Alembic reads it with the OS locale codec).

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

- Caddy serves the frontend from the `web` submodule mounted at `./web:/usr/share/caddy` (the
  build-branch artifacts live at the submodule root — `index.html` + `assets/`, no `dist/` subdir).
  The old `./web-submodule/dist` mount path was wrong and has been corrected.
- The `db` service uses `postgres:18`, whose image requires the data volume mounted at
  `/var/lib/postgresql` (not `/var/lib/postgresql/data`, which crash-loops). Already fixed in
  compose; keep it that way.
- DB migrations are **not** auto-run by the container; apply them manually with
  `uv run alembic upgrade head` after the `db` service is healthy.
- **USB webcam (`CAMERA_URL=0`) in the container**: works only on a Linux host with device
  passthrough (`devices: /dev/video0` + `group_add: video`, commented in compose by default).
  Docker Desktop (Windows/macOS) cannot pass USB through — run the backend natively for webcam,
  or use RTSP/file/synthetic in the container. A source that fails to open logs a clear ERROR and
  the app keeps running (no frames; snapshot → 503) rather than dying silently.
