FROM python:3.12-alpine
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY services/common/pyproject.toml services/common/pyproject.toml
COPY services/web-gateway/pyproject.toml services/web-gateway/pyproject.toml
RUN uv sync --package sense-gateway --frozen --no-dev --no-install-workspace
COPY services/common/sense_common/ services/common/sense_common/
COPY services/web-gateway/ services/web-gateway/
RUN uv sync --package sense-gateway --frozen --no-dev
EXPOSE 8080
HEALTHCHECK CMD wget -q --spider http://localhost:8080/health || exit 1
CMD ["uv", "run", "--package", "sense-gateway", "uvicorn", "gateway.main:app", "--host", "0.0.0.0", "--port", "8080"]
