FROM python:3.12-alpine AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
RUN apk add --no-cache gcc musl-dev linux-headers
WORKDIR /app

# Dependency layer (cached unless pyproject.toml or uv.lock changes)
COPY pyproject.toml uv.lock ./
COPY services/common/pyproject.toml services/common/pyproject.toml
COPY services/source-system/pyproject.toml services/source-system/pyproject.toml
RUN uv sync --package sense-source-system --frozen --no-dev --no-install-workspace

# Source layer (changes frequently)
COPY services/common/sense_common/ services/common/sense_common/
COPY services/source-system/ services/source-system/
RUN uv sync --package sense-source-system --frozen --no-dev

CMD ["uv", "run", "--package", "sense-source-system", "python", "-m", "system.main"]
