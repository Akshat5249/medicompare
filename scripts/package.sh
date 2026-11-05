#!/usr/bin/env bash
# Builds medicompare.zip from an allowlisted tree: no secrets, caches, dependencies or datasets.
set -euo pipefail
cd "$(dirname "$0")/.."
OUT="${1:-$(cd .. && pwd)}"
ZIP="$OUT/medicompare.zip"
TMP="$ZIP.tmp.zip"
cd ..
zip -qr "$TMP" medicompare \
  -x 'medicompare/.env' 'medicompare/.env.*.local' 'medicompare/backend/.venv/*' 'medicompare/backend/.env' \
  -x 'medicompare/frontend/node_modules/*' 'medicompare/frontend/.next/*' 'medicompare/frontend/coverage/*' \
  -x 'medicompare/frontend/test-results/*' 'medicompare/frontend/playwright-report/*' 'medicompare/frontend/next-env.d.ts' \
  -x 'medicompare/evaluation/datasets/*' 'medicompare/data/downloads/*.pdf' 'medicompare/PROGRESS.md' \
  -x '*/__pycache__/*' '*/.pytest_cache/*' '*/.mypy_cache/*' '*/.ruff_cache/*' '*/.hypothesis/*' '*.pyc' '*/.DS_Store' '*/.coverage' '*.tsbuildinfo' 'medicompare/frontend/.env*'
mv -f "$TMP" "$ZIP"
cd "$OUT"
shasum -a 256 medicompare.zip > SHA256SUMS
ls -la medicompare.zip; cat SHA256SUMS
