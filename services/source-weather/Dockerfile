FROM python:3.12-alpine AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app

# Dependency layer (cached unless pyproject.toml or uv.lock changes)
COPY pyproject.toml uv.lock ./
COPY services/common/pyproject.toml services/common/pyproject.toml
COPY services/source-weather/pyproject.toml services/source-weather/pyproject.toml
RUN uv sync --package sense-source-weather --frozen --no-dev --no-install-workspace

# Source layer (changes frequently)
COPY services/common/sense_common/ services/common/sense_common/
COPY services/source-weather/ services/source-weather/
RUN uv sync --package sense-source-weather --frozen --no-dev

CMD ["uv", "run", "--package", "sense-source-weather", "python", "-m", "weather.main"]
