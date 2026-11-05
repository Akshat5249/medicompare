#!/usr/bin/env bash
# Smoke test against the running stack through the same origin a browser uses.
set -euo pipefail
BASE="${BASE_URL:-http://localhost:3000}"
JAR="$(mktemp)"
trap 'rm -f "$JAR"' EXIT
pass=0
check() { # name expected-status url [curl args...]
  local name="$1" expected="$2" url="$3"; shift 3
  local status
  status="$(curl -s -o /dev/null -w '%{http_code}' -b "$JAR" -c "$JAR" "$@" "$BASE$url")"
  if [[ "$status" != "$expected" ]]; then echo "FAIL $name: expected $expected, got $status"; exit 1; fi
  echo "ok   $name ($status)"; pass=$((pass + 1))
}
check "frontend en" 200 /en
check "frontend hi" 200 /hi
check "frontend ta" 200 /ta
check "api ready" 200 /api/v1/health/ready
check "search" 200 "/api/v1/search?q=metformin"
check "janaushadhi" 200 "/api/v1/jan-aushadhi/kendras?pin=600001"
check "private needs auth" 401 /api/v1/prescriptions
CSRF="$(curl -s -b "$JAR" -c "$JAR" -X POST "$BASE/api/v1/auth/guest" | python3 -c 'import json,sys;print(json.load(sys.stdin)["csrf_token"])')"
BODY='{"items":[{"name":"Cetirizine","strength":"10 mg","form":"Tab"}]}'
check "csrf enforced" 403 /api/v1/prescriptions/manual -X POST -H 'Content-Type: application/json' -d "$BODY"
RX="$(curl -s -b "$JAR" -c "$JAR" -X POST -H "X-CSRF-Token: $CSRF" -H 'Content-Type: application/json' -d "$BODY" "$BASE/api/v1/prescriptions/manual")"
PID="$(echo "$RX" | python3 -c 'import json,sys;print(json.load(sys.stdin)["id"])')"
IID="$(echo "$RX" | python3 -c 'import json,sys;print(json.load(sys.stdin)["items"][0]["id"])')"
check "gate blocks unverified" 409 "/api/v1/prescriptions/$PID/items/$IID/prices"
check "cleanup" 204 "/api/v1/me" -X DELETE -H "X-CSRF-Token: $CSRF"
echo "SMOKE PASS: $pass checks"
