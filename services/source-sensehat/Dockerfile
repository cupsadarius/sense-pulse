FROM python:3.12-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# System deps for Pillow (required by sense-hat) and I2C tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    libopenjp2-7 \
    i2c-tools \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependency layer (cached unless pyproject.toml or uv.lock changes)
COPY pyproject.toml uv.lock ./
COPY services/common/pyproject.toml services/common/pyproject.toml
COPY services/source-sensehat/pyproject.toml services/source-sensehat/pyproject.toml
RUN uv sync --package sense-source-sensehat --frozen --no-dev --no-install-workspace \
    --python-preference system

# Source layer (changes frequently)
COPY services/common/sense_common/ services/common/sense_common/
COPY services/source-sensehat/ services/source-sensehat/
RUN uv sync --package sense-source-sensehat --frozen --no-dev \
    --python-preference system

CMD ["uv", "run", "--package", "sense-source-sensehat", "python", "-m", "sensehat.main"]
