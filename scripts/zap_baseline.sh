#!/usr/bin/env bash
# OWASP ZAP baseline (passive scan) of the running frontend.
set -uo pipefail
cd "$(dirname "$0")/.."
OUT="verification/security"; mkdir -p "$OUT"; chmod 777 "$OUT" 2>/dev/null
docker run --rm --add-host=host.docker.internal:host-gateway -v "$PWD/$OUT:/zap/wrk:rw" -v "$PWD/scripts/zap-rules.tsv:/zap/wrk/zap-rules.tsv:ro" \
  ghcr.io/zaproxy/zaproxy:stable zap-baseline.py -t "http://host.docker.internal:3000/en" -c zap-rules.tsv -r zap-report.html -m 2 -I
