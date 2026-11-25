FROM  python:3.12-slim-bookworm

WORKDIR /app

COPY src/ /app/src/ 
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
COPY  pyproject.toml .
COPY  README.md .
COPY  LICENSE . 
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_NO_CACHE=1
RUN uv sync --no-dev
ENV PATH="/app/.venv/bin:$PATH"
WORKDIR /app/src
RUN groupadd --system --gid 10001 appuser && \
    useradd --system --uid 10001 --gid appuser --no-create-home --shell /usr/sbin/nologin appuser

USER 10001

CMD [ "gunicorn", "backend.infrastructure.config.wsgi:application", "--bind", "0.0.0.0:8000"]