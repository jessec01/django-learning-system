FROM  python:3.12-slim-bookworm

WORKDIR /the/workdir/path

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --extra prod --no-cache

COPY src ./src

RUN useradmin --uid 10001 --create-home app

USER 10001

CMD ["uv", "run", "--no-dev", "gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]