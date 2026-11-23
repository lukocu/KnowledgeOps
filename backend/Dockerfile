FROM ghcr.io/astral-sh/uv:0.9.30-python3.14-bookworm-slim

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project

COPY app ./app
COPY migrations ./migrations

RUN useradd --system --uid 10001 --no-create-home app
USER app

EXPOSE 8000
CMD ["fastapi", "run", "app/main.py", "--port", "8000"]
