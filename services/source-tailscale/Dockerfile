FROM python:3.12-alpine AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
RUN apk add --no-cache tailscale
WORKDIR /app

# Dependency layer (cached unless pyproject.toml or uv.lock changes)
COPY pyproject.toml uv.lock ./
COPY services/common/pyproject.toml services/common/pyproject.toml
COPY services/source-tailscale/pyproject.toml services/source-tailscale/pyproject.toml
RUN uv sync --package sense-source-ts --frozen --no-dev --no-install-workspace

# Source layer (changes frequently)
COPY services/common/sense_common/ services/common/sense_common/
COPY services/source-tailscale/ services/source-tailscale/
RUN uv sync --package sense-source-ts --frozen --no-dev

CMD ["uv", "run", "--package", "sense-source-ts", "python", "-m", "tailscale.main"]
