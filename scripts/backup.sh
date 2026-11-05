#!/usr/bin/env bash
# Production backup: encrypted database dump. Object storage is deliberately excluded from
# long-term backup so that deleted prescriptions cannot return. See docs/OPERATIONS.md.
set -euo pipefail
: "${BACKUP_PASSPHRASE_FILE:?set BACKUP_PASSPHRASE_FILE}"
OUT="${1:-backups}"; mkdir -p "$OUT"
FILE="$OUT/medicompare-$(date -u +%Y%m%dT%H%M%SZ).dump.gpg"
docker compose exec -T postgres pg_dump -U "${POSTGRES_USER:-medicompare}" -d "${POSTGRES_DB:-medicompare}" -Fc \
  | gpg --batch --symmetric --cipher-algo AES256 --passphrase-file "$BACKUP_PASSPHRASE_FILE" -o "$FILE"
find "$OUT" -name 'medicompare-*.dump.gpg' -mtime +14 -delete
echo "wrote $FILE"
