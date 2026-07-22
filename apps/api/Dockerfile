# Backend image for Personal Job Application OS.
# Build context = apps/api (see render.yaml / docker build -f apps/api/Dockerfile apps/api).
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps kept minimal; psycopg2-binary ships its own libpq.
COPY pyproject.toml ./
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./

# Install the API plus Postgres drivers (asyncpg for the app, psycopg2 for Alembic).
RUN pip install --upgrade pip && pip install ".[postgres]" psycopg2-binary

COPY docker-entrypoint.sh ./docker-entrypoint.sh
RUN chmod +x ./docker-entrypoint.sh

EXPOSE 8000
CMD ["./docker-entrypoint.sh"]
