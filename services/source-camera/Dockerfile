FROM python:3.12-alpine

# FFmpeg for HLS streaming
RUN apk add --no-cache ffmpeg

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy shared library
COPY services/common /app/services/common

# Copy service code
COPY services/source-camera /app/services/source-camera

# Install dependencies
RUN uv pip install --system --no-cache \
    /app/services/common \
    /app/services/source-camera

# HLS output directory
RUN mkdir -p /hls
VOLUME ["/hls"]

ENV MODE=stream
ENV HLS_OUTPUT_DIR=/hls

CMD ["python", "-m", "camera.main"]
