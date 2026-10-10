FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/apps/backend/.venv/bin:$PATH"

WORKDIR /app/apps/backend

COPY packages/ved-db /app/packages/ved-db
COPY apps/backend/pyproject.toml apps/backend/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-dev

COPY mcp-servers/reminders/pyproject.toml mcp-servers/reminders/uv.lock \
     /app/mcp-servers/reminders/
RUN --mount=type=cache,target=/root/.cache/uv \
    cd /app/mcp-servers/reminders \
    && uv sync --locked --no-install-project --no-dev

COPY mcp-servers/reminders /app/mcp-servers/reminders
RUN --mount=type=cache,target=/root/.cache/uv \
    cd /app/mcp-servers/reminders && uv sync --locked --no-dev

COPY mcp-servers/people/pyproject.toml mcp-servers/people/uv.lock \
     /app/mcp-servers/people/
RUN --mount=type=cache,target=/root/.cache/uv \
    cd /app/mcp-servers/people \
    && uv sync --locked --no-install-project --no-dev

COPY mcp-servers/people /app/mcp-servers/people
RUN --mount=type=cache,target=/root/.cache/uv \
    cd /app/mcp-servers/people && uv sync --locked --no-dev

COPY mcp-servers/memory/pyproject.toml mcp-servers/memory/uv.lock \
     /app/mcp-servers/memory/
RUN --mount=type=cache,target=/root/.cache/uv \
    cd /app/mcp-servers/memory \
    && uv sync --locked --no-install-project --no-dev

COPY mcp-servers/memory /app/mcp-servers/memory
RUN --mount=type=cache,target=/root/.cache/uv \
    cd /app/mcp-servers/memory && uv sync --locked --no-dev

COPY apps/backend/ ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

RUN useradd --create-home --uid 1000 ved && chown -R ved:ved /app
USER ved

EXPOSE 8000

CMD ["uvicorn", "ved_backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
