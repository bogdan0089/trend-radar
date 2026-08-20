#!/usr/bin/env bash
# End-to-end check of an already running stack.
#
# It walks the same path a reviewer takes by hand: the panel is closed without a
# token, the seeded admin can sign in, the dashboard returns products carrying
# all seven required fields with a score and a reasoning, the Sales Boost list
# answers, and the manual run button queues a Celery task instead of blocking.
#
# Usage: docker compose up -d && ./scripts/smoke.sh

set -euo pipefail

API="${API_URL:-http://localhost:8011}"
WEB="${WEB_URL:-http://localhost:3011}"
USERNAME="${ADMIN_USERNAME:-admin}"
PASSWORD="${ADMIN_PASSWORD:-admin123}"

# The JSON assertions need an interpreter. `python3` is picked first because
# that is the name on CI, but on Windows it is a Microsoft Store stub that
# exits non-zero, so each candidate is tried rather than assumed.
PYTHON=""
for candidate in python3 python; do
    if command -v "$candidate" > /dev/null 2>&1 && "$candidate" -c 'import json' > /dev/null 2>&1; then
        PYTHON="$candidate"
        break
    fi
done
[ -n "$PYTHON" ] || { echo "no working python found" >&2; exit 1; }

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

step() { printf '\n==> %s\n' "$1"; }
fail() { printf 'FAILED: %s\n' "$1" >&2; exit 1; }

step "health"
curl -fsS "$API/api/health" -o "$work/health.json"
"$PYTHON" - "$work/health.json" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
assert data["status"] == "ok", data
assert data["database"] == "ok", data
print("ok, llm_provider =", data["llm_provider"])
PY

step "the panel is closed without a token"
code=$(curl -s -o /dev/null -w '%{http_code}' "$API/api/products")
[ "$code" = "401" ] || fail "expected 401 without a token, got $code"
echo "ok, 401"

step "login as the seeded admin"
curl -fsS -X POST "$API/api/auth/login" \
    -H 'Content-Type: application/json' \
    -d "{\"username\":\"$USERNAME\",\"password\":\"$PASSWORD\"}" \
    -o "$work/login.json"
token=$("$PYTHON" -c 'import json,sys; print(json.load(open(sys.argv[1]))["access_token"])' "$work/login.json")
[ -n "$token" ] || fail "no access_token in the login response"
auth="Authorization: Bearer $token"
echo "ok, token received"

step "products carry the seven required fields, a score and a reasoning"
curl -fsS "$API/api/products?limit=5" -H "$auth" -o "$work/products.json"
"$PYTHON" - "$work/products.json" <<'PY'
import json, sys

data = json.load(open(sys.argv[1]))
items = data["items"]
assert items, "the seed left no products, the dashboard would be empty"

# The seven fields the spec requires for every product.
required = (
    "title", "category", "price", "rating",
    "reviews_count", "product_url", "image_url",
)
for item in items:
    missing = [f for f in required if f not in item]
    assert not missing, f"{item.get('asin')}: missing fields {missing}"
    assert item["title"] and item["category"], f"{item.get('asin')}: empty title or category"
    assert item["product_url"].startswith("http"), item["product_url"]

scored = [i for i in items if i.get("score")]
assert scored, "not one product has a score, scoring never ran"

for item in scored:
    score = item["score"]
    assert 0 <= score["score"] <= 100, score
    assert score["reasoning"].strip(), f"{item['asin']}: empty reasoning"

print(f"ok, {data['total']} products, {len(scored)} of {len(items)} on this page are scored")
PY

step "sales boost list"
curl -fsS "$API/api/sales-boost?limit=5" -H "$auth" -o "$work/past.json"
"$PYTHON" - "$work/past.json" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
print(f"ok, {data['total']} past products")
PY

step "the manual run button queues a task without blocking"
code=$(curl -s -o "$work/run.json" -w '%{http_code}' -X POST "$API/api/scrape-runs" -H "$auth")
[ "$code" = "202" ] || fail "expected 202 from POST /api/scrape-runs, got $code"
"$PYTHON" - "$work/run.json" <<'PY'
import json, sys
run = json.load(open(sys.argv[1]))
assert run["status"] in ("pending", "running"), run
print(f"ok, run #{run['id']} is {run['status']}, the API returned straight away")
PY

step "the frontend serves the SPA"
curl -fsS "$WEB/" -o "$work/index.html"
grep -q "Trend Radar" "$work/index.html" || fail "the frontend did not return the app shell"
echo "ok"

printf '\nAll smoke checks passed.\n'
