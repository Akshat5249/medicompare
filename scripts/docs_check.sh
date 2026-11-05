#!/usr/bin/env bash
# Renders Mermaid diagrams, validates OpenAPI and checks internal Markdown links.
set -euo pipefail
cd "$(dirname "$0")/.."
count=0
for file in docs/diagrams/*.mmd; do
  name="$(basename "$file" .mmd)"
  for format in svg png; do
    docker run --rm -u "$(id -u):$(id -g)" -v "$PWD/docs/diagrams:/data" minlag/mermaid-cli:11.4.2 \
      -i "/data/$name.mmd" -o "/data/$name.$format" -b white --quiet
    [[ -s "docs/diagrams/$name.$format" ]] || { echo "FAIL render $name.$format"; exit 1; }
  done
  count=$((count + 1)); echo "rendered $name"
done
echo "diagrams rendered: $count"
backend/.venv/bin/python scripts/check_docs.py
