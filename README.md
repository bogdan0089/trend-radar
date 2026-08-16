# Trend Radar

MVP сервісу парсингу, AI-скорингу та аналітики трендових товарів (Amazon).

> 🚧 У розробці. Повний README (архітектурна схема, інструкція запуску, тестовий
> логін/пароль) заповнюється на кроці 8.

## Швидкий старт

```bash
cp .env.example .env
docker compose up --build
```

- API: http://localhost:8011/api/health
- Swagger: http://localhost:8011/docs

Тестовий логін (створюється автоматично): **admin / admin123**

Порти на хості нестандартні (8011 / 5442 / 6390 / 3011), щоб не конфліктувати
з іншими локальними стеками. Змінюються в `.env`.

## Стек

FastAPI · SQLAlchemy 2 · Alembic · PostgreSQL 16 · Redis 7 · Celery + Beat ·
Playwright · Vue 3 · Docker Compose

## Прогрес

- [x] Крок 1 — каркас: compose, Postgres, Redis, API, worker, beat, Alembic
- [x] Крок 2 — моделі, міграція, JWT-авторизація, автосід адміна
- [ ] Крок 3 — Playwright-парсер Amazon
- [ ] Крок 4 — Google Trends + Sales Boost + boost-алгоритм
- [ ] Крок 5 — скоринг (LLM + fallback) і Celery-пайплайн
- [ ] Крок 6 — Vue: логін і дашборд
- [ ] Крок 7 — Vue: Sales Boost
- [ ] Крок 8 — README і фінальна чиста перевірка