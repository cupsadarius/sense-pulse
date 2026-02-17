FROM python:3.12-alpine AS builder

# BLE dependencies
RUN apk add --no-cache bluez bluez-dev gcc musl-dev

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app

# Dependency layer (cached unless pyproject.toml or uv.lock changes)
COPY pyproject.toml uv.lock ./
COPY services/common/pyproject.toml services/common/pyproject.toml
COPY services/source-aranet4/pyproject.toml services/source-aranet4/pyproject.toml
RUN uv sync --package sense-source-aranet4 --frozen --no-dev --no-install-workspace

# Source layer (changes frequently)
COPY services/common/sense_common/ services/common/sense_common/
COPY services/source-aranet4/ services/source-aranet4/
RUN uv sync --package sense-source-aranet4 --frozen --no-dev

ENV MODE=poll

CMD ["uv", "run", "--package", "sense-source-aranet4", "python", "-m", "aranet4_svc.main"]
