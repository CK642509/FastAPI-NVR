FROM python:3.12-slim

# OpenCV(headless) / PyAV 執行期所需的系統函式庫
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# 安裝 uv（套件管理）
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

# 先裝相依（利用 Docker layer 快取）
COPY pyproject.toml uv.lock* ./
RUN uv sync --no-dev

# 再複製程式碼
COPY app ./app
COPY main.py ./

# 持續錄影；以 -m 執行套件進入點
CMD ["python", "-m", "app.main"]
