#!/usr/bin/env bash
# Locust against the running backend. Rate limiting is on, so the test runs from one address
# with the public limit raised only in this local run. See docs/TEST_PLAN.md.
set -euo pipefail
cd "$(dirname "$0")/.."
OUT="verification/perf"
mkdir -p "$OUT"
USERS="${USERS:-50}" RATE="${RATE:-10}" DURATION="${DURATION:-3m}"
docker run --rm --network host -v "$PWD/scripts:/mnt/scripts:ro" -v "$PWD/$OUT:/mnt/out" locustio/locust:2.37.0 \
  -f /mnt/scripts/locustfile.py --headless -u "$USERS" -r "$RATE" -t "$DURATION" \
  --host "${BASE_URL:-http://localhost:8000}" --csv /mnt/out/locust --only-summary
python3 - "$OUT/locust_stats.csv" <<'PY'
import csv, sys
for row in csv.DictReader(open(sys.argv[1])):
    print(f"{row['Name']:<14} requests={row['Request Count']:>6} failures={row['Failure Count']:>4} "
          f"p50={row['50%']}ms p95={row['95%']}ms p99={row['99%']}ms rps={float(row['Requests/s']):.1f}")
PY
