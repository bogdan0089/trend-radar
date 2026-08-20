#!/usr/bin/env bash
# One entrypoint for every service. No manual steps after `docker compose up`.
set -e

echo "[entrypoint] waiting for postgres at ${POSTGRES_HOST}:${POSTGRES_PORT} ..."
python - <<'PY'
import os, sys, time
import psycopg

dsn = "host={h} port={p} user={u} password={pw} dbname={db}".format(
    h=os.getenv("POSTGRES_HOST", "postgres"),
    p=os.getenv("POSTGRES_PORT", "5432"),
    u=os.getenv("POSTGRES_USER", "trend"),
    pw=os.getenv("POSTGRES_PASSWORD", "trend"),
    db=os.getenv("POSTGRES_DB", "trend_radar"),
)

for attempt in range(60):
    try:
        with psycopg.connect(dsn, connect_timeout=3):
            print("[entrypoint] postgres is up")
            sys.exit(0)
    except Exception as exc:
        print(f"[entrypoint] postgres not ready ({attempt + 1}/60): {exc}")
        time.sleep(2)

print("[entrypoint] postgres did not become ready in time")
sys.exit(1)
PY

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
    echo "[entrypoint] running alembic migrations ..."
    alembic upgrade head

    echo "[entrypoint] seeding ..."
    python -m app.seed
fi

echo "[entrypoint] starting: $*"
exec "$@"