# Security and privacy

See also [THREAT_MODEL.md](THREAT_MODEL.md). Scan results are in the verification report.

## Data we hold
| Data | Stored | Retention |
|---|---|---|
| Search queries | Not stored | None. Not logged by the application |
| Location for Kendra search | Not stored (request only) | None |
| Account email, Argon2id password hash | Yes | Until account deletion |
| Prescription image | Private bucket, metadata stripped | 7 days by default, then deleted |
| Extracted text, candidates, verification events | Database | Same as the prescription |
| Consent records | Database | Until account deletion |
| Audit events | Identifiers and counts only, never prescription text | Actor link removed on account deletion |

## Controls
- **Authentication:** Argon2id; session token in an `httpOnly`, `SameSite=Lax` cookie (`Secure` required in production); only keyed hashes of session and share tokens are stored.
- **CSRF:** per-session token required on state changes, plus an `Origin` check.
- **Abuse limits:** per-address limits (public 300/min, auth 20/min, upload 30/hour), account lockout after 5 failures with doubling backoff up to 24 hours, equal-time login failures.
- **Authorization:** owners only, and other people's records return 404. Pharmacists reach a prescription only through an active share that names them.
- **Uploads:** magic-byte type check, 10 MB, 5 pages, 40 MP limit, encrypted PDFs refused, decompression-bomb protection, pixel re-encode. PDF pages are rendered to pixels before OCR. ClamAV hook fails closed when configured.
- **Headers:** nonce-based CSP on the frontend, `default-src 'none'` on the API, `X-Frame-Options`, `nosniff`, HSTS in production. Inline styles are allowed, since the React `style` attribute is used for span overlays; inline scripts are not.
- **Errors:** RFC 9457 problem details. Validation errors never echo input.
- **Logs:** structured JSON with event names and identifiers, without prescription content.
- **Untrusted content:** text in files is data. There is no instruction channel in the deterministic pipeline. The optional LLM adapter sees only filtered lines inside a delimited block, its output must pass a schema and appear verbatim in the input, and it never chooses a match.
- **Analytics:** none.
- **Secrets:** only `.env.example` ships. Production Compose refuses to start without secrets, and settings refuse default keys in production. Development-only defaults in `docker-compose.yml` bind to localhost and are allowlisted in Gitleaks with this explanation.

## Least privilege
- **Containers:** application images run as uid 10001; the database, Redis and MinIO have no published ports in production.
- **Database roles:** **not implemented.** The application uses one database role. Before production, split the migration role from a runtime role with no DDL.
- **Storage:** the application holds one credential for one private bucket.

## Encryption
- **In transit:** Caddy terminates TLS in production. Traffic between containers stays on a private Docker network, unencrypted.
- **At rest:** **not provided by the application.** Use encrypted volumes from the host or cloud provider, and see [DEPLOYMENT.md](DEPLOYMENT.md). Backups are encrypted by `scripts/backup.sh`.

## Deletion
- **Upload deletion and account deletion** remove objects first, then rows. Tests assert both.
- **Retention job:** hourly. Removes expired prescriptions, guests and sessions.
- **Backups:** only the database is backed up, encrypted, for 14 days. Object storage is deliberately not backed up. A deleted prescription's rows can therefore persist in backups for up to 14 days, after which they age out. On restore, rerun the retention job, and replay a deletion log if one is kept. **State this in the privacy notice before launch.**

## Known gaps
Single database role; no at-rest encryption from the application; no independent penetration test; rate limits are per address and behind a shared NAT may affect several users; no MFA for admins (add before production).
