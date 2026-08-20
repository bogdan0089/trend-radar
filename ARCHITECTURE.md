# Architecture

The rules the code actually follows. For the diagram and the request flow, see
the [README](README.md).

## Flow

```
HTTP    →  router  →  service  →  repository  →  PostgreSQL
                         ↓
Celery  →  task    →  service  →  repository
                         ↓
                      scraper / llm / scoring
                      (the outside world and pure maths)
```

The same service layer serves both HTTP and Celery. A task is as thin a caller
as a router is.

## Layers and their rules

### `app/api/routers/` — transport
- Validates input (a Pydantic schema), calls **one** service method, returns a
  response schema.
- Owns the ORM -> DTO conversion: services hand back ORM rows or dataclasses and
  the router turns them into the `response_model`. Nothing else serialises.
- Contains **no** business logic and no database queries.
- `HTTPException` and HTTP status codes live here and nowhere else.

### `app/services/` — business logic
- All of it: rules, calculations, orchestration, import reports.
- Owns the transaction — the service decides when to `commit`.
- Raises domain exceptions from `app/core/exceptions.py`, **never**
  `HTTPException`: a service does not know it is running under HTTP.
- Knows nothing about `Request`, `Depends` or Celery.

### `app/repositories/` — data access
- SQLAlchemy queries only: `get`, `list`, `create`, `update`, `upsert`.
- **Never** commits (`flush()` at most, to obtain an id).
- No rules, no decisions. An `if` about business logic in a repository is in the
  wrong file.

### The rest
- `app/models/` — ORM tables. Schema only, no methods carrying logic.
- `app/schemas/` — Pydantic DTOs for API input and output, named after the API
  resource they serve. ORM objects never reach the client.
- `app/celery/` — the Celery app, its beat schedule and its tasks. Tasks are
  thin: open a session, call a service, log.
- `app/utils/` — pure helpers with no database, network or config.
- `app/core/` — config, logging, security (JWT and hashing), domain exceptions.
- `app/integrations/` — the outside world: Playwright scrapers, LLM adapters.
  Isolated behind an interface so no service depends on a specific provider.

## Integrations are split in two

Every scraper is a **pure parsing function** plus a **thin browser driver**:

| Part | Example | Tested |
| --- | --- | --- |
| Parsing | `parse_bestsellers(html)`, `parse_widget_payload(raw)` | against saved snapshots, in milliseconds, no Chromium |
| Driving | `AmazonScraper`, `GoogleTrendsScraper` | returns HTML or JSON and nothing else |

That split is why the parser tests are fast and deterministic, why the same
parser serves both a live scrape and the bundled snapshot, and why a layout
change on Amazon means fixing exactly one function.

## Transactions

- HTTP: `get_db` hands over a session, the service commits, the router stays out
  of it.
- Celery: `session_scope()` commits on exit and rolls back on an exception.
- A repository receives its session from outside and never manages it.

## Logging

One configuration in `app/core/logging.py`, wired up in `main.py` and in
`celery_app.py`. Loggers are taken as `logging.getLogger(__name__)`, so the
layer is visible from the logger name.

Always logged:
- the start and finish of every Celery task, with duration and result;
- every scrape attempt: the URL, how many products were found, whether the
  anti-bot page appeared;
- the scoring branch taken — `llm` or `fallback` — and **why** (no key, timeout,
  invalid JSON);
- every authentication failure.

Never logged: passwords, tokens, `LLM_API_KEY`.
