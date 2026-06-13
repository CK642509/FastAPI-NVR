# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

This is an **early-stage / pre-implementation** project. The committed backend files
(`backend/main.py`, `backend/Dockerfile`, `caddy/Caddyfile`) are empty placeholders — the
actual code has not been written yet. The authoritative spec for what to build lives in `docs/`:

- `docs/proposal.md` — the proposal: tech stack table, system architecture diagram, and the
  dated Phase 1–5 timeline.
- `docs/milestone.md` — feature breakdown per phase.
- `docs/ooa.md` — incremental OOA/OOD class diagrams (Mermaid) per phase, plus the cumulative
  full-system class diagram. **This is the design contract**: class names, responsibilities, and
  relationships defined here are what the implementation should follow.

When implementing a feature, find its phase in `docs/ooa.md` first — the class structure,
abstract base classes, and design patterns are already specified there.

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

- **`FrameAnalyzer` (abstract, Template Method)** — `MotionDetector` (Phase 2/3, OpenCV MOG2) and
  `AIAnalyzer` (Phase 4, YOLO) both subclass it. `EventService` consumes `AnalysisResult` and does
  not care which analyzer produced it.
- **`NotificationStrategy` (abstract, Strategy Pattern)** — `TelegramNotifier`, `DiscordNotifier`.
  Adding a notification channel means adding one class, not touching `EventService`.
- **`EventService` (Facade)** — coordinates event creation, `EventRecorder` (pre/post-event ring
  buffer clipping), notifications, and `WebSocketManager` broadcast to the frontend.
- **Repository Pattern** — `CameraRepository` / `EventRepository` isolate SQLAlchemy data access.
- **`CameraManager` (Facade, Phase 4)** — owns the lifecycle of multiple `VideoPipeline`s and their
  `ReconnectionManager`s.

Request flow: browser → Caddy (`:80`/`:443`) → Vue frontend (static) or FastAPI; Caddy also serves
recorded video directly from `/media/*` for performance. FastAPI can push config changes into a
running `VideoPipeline` dynamically.

## Known caveats

- `docker-compose.yaml` mounts the frontend from `./web-submodule/dist`, but the submodule is
  actually at `web` (per `.gitmodules`). Verify/reconcile this path before relying on the Caddy
  static mount.
- Docs note the stack as Postgres 18 (`docs/proposal.md`) while `docker-compose.yaml` pins
  `postgres:15-alpine`.
