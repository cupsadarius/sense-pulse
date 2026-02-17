# ---------- Stage 1: compile RTIMULib (undeclared C dep of sense-hat) ----------
FROM python:3.12-slim-bookworm AS rtimu-builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake git python3-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir setuptools

RUN git clone --depth 1 https://github.com/RPi-Distro/RTIMULib.git /tmp/RTIMULib \
    && cd /tmp/RTIMULib/Linux/python \
    && python setup.py build_ext \
    && python setup.py install

# Stage the compiled RTIMU files into a clean directory for easy COPY
RUN mkdir /rtimu \
    && cp /usr/local/lib/python3.12/site-packages/RTIMU*.so /rtimu/ \
    && cp -r /usr/local/lib/python3.12/site-packages/RTIMU*.egg-info /rtimu/

# ---------- Stage 2: runtime image ----------
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

# Install RTIMULib into uv's venv.  sense-hat imports RTIMU at runtime but
# does not declare it as a pip dependency — it is only available as a system
# package on Raspberry Pi OS or compiled from source.
COPY --from=rtimu-builder /rtimu/ /app/.venv/lib/python3.12/site-packages/

CMD ["uv", "run", "--package", "sense-source-sensehat", "python", "-m", "sensehat.main"]
