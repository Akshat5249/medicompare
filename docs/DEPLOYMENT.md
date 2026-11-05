# Deployment

**Nothing has been deployed from this build, and there is no live URL.** The production Compose file's syntax is checked by `make verify`. These steps have not been run on a real server.

## Target
One DigitalOcean droplet in Bangalore, chosen so data stays in India pending [legal review](COMPLIANCE_NOTES.md). The stack's resource limits add up to about 5 GB, so use **8 GB / 4 vCPU**.

### Cost estimate
| Item | Monthly | Source |
|---|---|---|
| Droplet, 8 GiB / 4 vCPU | US$48 | [DigitalOcean pricing](https://www.digitalocean.com/pricing/droplets), read 2026-11-05 |
| Weekly droplet backups (optional) | Not priced here | Check the same page |
| Domain | Varies | Registrar |

Without ClamAV, a 4 GiB / 2 vCPU droplet at US$24 could run a demo. OCR would be slower and this was not tested. Production should keep ClamAV.

## Steps
1. **Create** an Ubuntu droplet in `BLR1`, with an encrypted volume for `/var/lib/docker/volumes` (the application does not encrypt at rest).
2. **Firewall:** allow only 22 (restricted to your address), 80 and 443.
3. **DNS:** point your domain's A record at the droplet.
4. **Install** Docker Engine and the Compose plugin.
5. **Fetch** this repository to `/opt/medicompare`.
6. **Create `.env`:**
   ```
   DOMAIN=your.domain
   SECRET_KEY=<openssl rand -hex 32>
   POSTGRES_USER=medicompare
   POSTGRES_PASSWORD=<openssl rand -hex 24>
   POSTGRES_DB=medicompare
   S3_ACCESS_KEY=<openssl rand -hex 16>
   S3_SECRET_KEY=<openssl rand -hex 32>
   ```
7. **Start:**
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build --wait
   ```
8. **Create an admin** (prompts for a password):
   ```bash
   docker compose exec backend python -m app.cli create-admin you@your.domain
   ```
9. **Import real data** from the admin page or the CLI. The production profile loads no demo data, so the catalogue starts empty. Sources must exist first, so run the `import` CLI command, which creates them.
10. **Smoke test:**
   ```bash
   BASE_URL=https://your.domain bash scripts/smoke.sh
   ```

## Environment variables
Listed in [`.env.example`](../.env.example). Production refuses a short `SECRET_KEY` and a false `COOKIE_SECURE`.

## Migrations
`migrate` runs `alembic upgrade head` before the backend starts. Take a backup first. Write backward-compatible migrations so that a rollback of the application can use the newer schema.

## Rollback
1. Check out the previous tag.
2. `docker compose ... up -d --build --wait`.
3. If a migration must be undone, restore the backup taken before it. Prefer that to untested `alembic downgrade`.

## Backups
`scripts/backup.sh` writes an encrypted database dump, kept for 14 days. Run it from cron. `make backup-test` checks backup and restore into a scratch database; object storage is deliberately excluded. See [OPERATIONS.md](OPERATIONS.md).

## Monitoring
- **Health:** `/api/v1/health/ready` with any uptime checker.
- **Logs:** JSON on stdout, read with `docker compose logs`. The application turns off access logs, because URLs can contain search text. Keep Caddy's access log off as well (the provided Caddyfile does not enable it).
- **Error tracking:** the `_unhandled` handler in `main.py` logs error type and path only. Add a tracking SDK there, with request bodies and URLs scrubbed.
