# Two targets from one file: shared code, different bases.
# api    -> slim python image, it needs no browser
# worker -> official Playwright image, Chromium and system libs preinstalled

# ---------- API ----------
FROM python:3.12-slim AS api

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x /app/entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# ---------- WORKER ----------
# noble (Ubuntu 24.04) ships Python 3.12, matching api. jammy ships 3.10,
# which lacks datetime.UTC and made the worker fail on import.
FROM mcr.microsoft.com/playwright/python:v1.49.1-noble AS worker

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x /app/entrypoint.sh

# The worker never runs migrations; api owns them
ENV RUN_MIGRATIONS=false
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["celery", "-A", "app.celery.celery_app.celery", "worker", "--loglevel=info", "--concurrency=2"]