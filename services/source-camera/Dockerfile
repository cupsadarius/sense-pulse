FROM python:3.12-alpine AS builder

# FFmpeg for HLS streaming
RUN apk add --no-cache ffmpeg

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app

# Dependency layer (cached unless pyproject.toml or uv.lock changes)
COPY pyproject.toml uv.lock ./
COPY services/common/pyproject.toml services/common/pyproject.toml
COPY services/source-camera/pyproject.toml services/source-camera/pyproject.toml
RUN uv sync --package sense-source-camera --frozen --no-dev --no-install-workspace

# Source layer (changes frequently)
COPY services/common/sense_common/ services/common/sense_common/
COPY services/source-camera/ services/source-camera/
RUN uv sync --package sense-source-camera --frozen --no-dev

# HLS output directory
RUN mkdir -p /hls
VOLUME ["/hls"]

ENV MODE=stream
ENV HLS_OUTPUT_DIR=/hls

CMD ["uv", "run", "--package", "sense-source-camera", "python", "-m", "camera.main"]
