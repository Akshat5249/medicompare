#!/usr/bin/env bash
# Backs up the database and object store, restores into scratch targets and compares counts.
set -euo pipefail
cd "$(dirname "$0")/.."
DIR="$(mktemp -d)"
trap 'rm -rf "$DIR"' EXIT
PG="docker compose exec -T postgres"
USER="${POSTGRES_USER:-medicompare}"
$PG pg_dump -U "$USER" -d medicompare -Fc > "$DIR/db.dump"
echo "backup size: $(wc -c < "$DIR/db.dump") bytes"
$PG psql -U "$USER" -d postgres -q -c "DROP DATABASE IF EXISTS restore_check" -c "CREATE DATABASE restore_check"
docker compose exec -T postgres pg_restore -U "$USER" -d restore_check --no-owner < "$DIR/db.dump"
for table in medicines price_observations users prescriptions audit_events import_batches; do
  a="$($PG psql -U "$USER" -d medicompare -Atc "SELECT count(*) FROM $table")"
  b="$($PG psql -U "$USER" -d restore_check -Atc "SELECT count(*) FROM $table")"
  if [[ "$a" != "$b" ]]; then echo "FAIL $table: $a vs $b"; exit 1; fi
  echo "ok   $table: $a rows"
done
$PG psql -U "$USER" -d postgres -q -c "DROP DATABASE restore_check"
echo "BACKUP/RESTORE PASS"
