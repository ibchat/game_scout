FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files
COPY pyproject.toml ./
RUN pip install --no-cache-dir poetry && \
    poetry config virtualenvs.create false && \
    poetry install --no-interaction --no-ansi

# Copy application code
COPY apps ./apps
COPY migrations ./migrations
COPY scripts ./scripts
COPY dev_supervisor ./dev_supervisor
COPY tests_contract ./tests_contract
COPY SPECS ./SPECS
COPY alembic.ini ./alembic.ini

# Create exports directory
RUN mkdir -p /data/exports

# Run migrations on startup
CMD ["sh", "-c", "alembic upgrade head && uvicorn apps.api.main:app --host 0.0.0.0 --port 8000"]