FROM python:3.12-alpine
RUN apk add --no-cache docker-cli docker-cli-compose
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY services/common/pyproject.toml services/common/pyproject.toml
COPY services/orchestrator/pyproject.toml services/orchestrator/pyproject.toml
RUN uv sync --package sense-orchestrator --frozen --no-dev --no-install-workspace
COPY services/common/sense_common/ services/common/sense_common/
COPY services/orchestrator/ services/orchestrator/
RUN uv sync --package sense-orchestrator --frozen --no-dev
CMD ["uv", "run", "--package", "sense-orchestrator", "python", "-m", "orchestrator.main"]
