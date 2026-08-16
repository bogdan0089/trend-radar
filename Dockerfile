# Два таргети з одного файлу — код спільний, бази різні.
# api    → легкий python:slim, браузери йому не потрібні
# worker → офіційний образ Playwright, там уже стоять Chromium і системні бібліотеки

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
FROM mcr.microsoft.com/playwright/python:v1.49.1-jammy AS worker

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x /app/entrypoint.sh

# Worker міграції не запускає — за них відповідає api
ENV RUN_MIGRATIONS=false
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["celery", "-A", "app.celery_app.celery", "worker", "--loglevel=info", "--concurrency=2"]