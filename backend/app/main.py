"""進入點：以 uvicorn 啟動 FastAPI 應用（Phase 2）。

`python -m app.main` 或 `python main.py` 皆等同於
`uvicorn app.server:app --host <HOST> --port <PORT>`。
"""

from __future__ import annotations

import uvicorn

from .config import settings


def main() -> None:
    uvicorn.run(
        "app.server:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
