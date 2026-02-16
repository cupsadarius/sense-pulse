FROM python:3.12-alpine

# BLE dependencies
RUN apk add --no-cache bluez bluez-dev gcc musl-dev

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy shared library
COPY services/common /app/services/common

# Copy service code
COPY services/source-aranet4 /app/services/source-aranet4

# Install dependencies
RUN uv pip install --system --no-cache \
    /app/services/common \
    /app/services/source-aranet4

ENV MODE=poll

CMD ["python", "-m", "aranet4_svc.main"]
