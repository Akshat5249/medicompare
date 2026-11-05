# Operations

## Routine jobs
| Job | Runs | Command |
|---|---|---|
| Retention | Hourly in `scheduler`, and on start | `python -m app.cli retention` |
| Backup | Daily via cron | `scripts/backup.sh` |
| Restore drill | Monthly | `make backup-test` (scratch database) |
| Data freshness | Weekly | Admin page, "Source freshness" |
| Data quality | After each import | `python -m app.cli quality` |
| Dependency scans | Weekly and in CI | `make security` |

## Importing data
```bash
docker compose exec backend python -m app.cli import nppa_ceiling nppa_ceiling /srv/data/sources/nppa_ceiling_prices.csv
docker compose exec backend python -m app.cli publish <batch_id>
```
Check the review queue on the admin page. Failed rows are never published, and can be corrected and revalidated before publication. A new price import adds observations, and the newest is shown.

Refreshing NPPA data:
```bash
bash data/importers/download_nppa.sh
backend/.venv/bin/python data/importers/nppa_pdf.py data/downloads data/sources/nppa_ceiling_prices.csv data/sources/nppa_parse_failures.csv
```
Update the `observed_at` in `normalize_nppa_row` to match the "As on" date in the new files.

## Restore
1. Stop `backend`, `worker` and `scheduler`.
2. Decrypt: `gpg --decrypt file.dump.gpg > db.dump`.
3. Restore: `docker compose exec -T postgres pg_restore -U medicompare -d medicompare --clean --no-owner < db.dump`.
4. **Run the retention job before reopening.** Prescription rows whose objects no longer exist should be reviewed: restored rows may refer to images deleted since the backup.
5. Start services and run the smoke test.

## Incident response
| Situation | First actions |
|---|---|
| **Suspected data breach** | Take the stack offline. Preserve logs and volumes. Rotate `SECRET_KEY` (signs out everyone and invalidates share links), database and storage credentials. Assess what was exposed. Get legal advice on notification duties under DPDP ([COMPLIANCE_NOTES.md](COMPLIANCE_NOTES.md)) |
| **Wrong price or data published** | Correct by importing a corrected batch. To hide a batch immediately, delete its observations by `batch_id` in SQL, then record what happened |
| **Safety bug** (unverified item reaches comparison) | Treat as severity 1. Disable prescription routes at the proxy, add a failing test, fix, and rerun the safety suite before re-enabling |
| **OCR queue backlog** | Check `worker` logs. Scale with `docker compose up -d --scale worker=2` if resources allow. Manual entry still works |
| **Redis down** | Public reads continue. Login, register and upload return 503 by design, and OCR waits |

## Rotating `SECRET_KEY`
Session and share tokens are hashed with this key, so rotation signs out all users and invalidates all share links.

## Logging rules
Never log prescription text, search text, images or tokens. Reviewers should treat any log line containing them as a bug.
