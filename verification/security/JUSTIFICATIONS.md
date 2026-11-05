**Accepted, one package: pcre2 10.32 in `medicompare-backend` and `medicompare-worker`** (2 critical and 5 high CVEs: CVE-2022-1586, CVE-2022-1587, CVE-2019-20454, CVE-2026-103111, CVE-2026-86145, CVE-2026-89157, CVE-2026-89161).
- **Where:** a Red Hat build of the library bundled in the `opencv-python` and `psycopg-binary` wheels. The Debian system library is patched, at 10.42-1+deb12u2.
- **Why accepted:** exploiting these needs an attacker-controlled regular expression compiled by that copy of the library. MediCompare passes no user input to it, and Python's `re` does not use it. This reasoning comes from code review, and was not proven by testing.
- **Not fixed because:** the fix is in upstream wheels. `psycopg[c]` would remove one copy at the cost of a compiler in the build, and `rapidocr-onnxruntime` requires `opencv-python`.
- **Action:** recheck on each dependency update. Listed in `.trivyignore`, so the gate passes only because of this explicit decision.

**Fixed during the build:** removed `uv` and `setuptools` from the Python runtime images, moved the frontend to a runtime image without npm, overrode PostCSS under Next.js to 8.5.x, and applied Debian updates.

**Gitleaks scope:** `.next`, `node_modules`, `.venv` and test output are excluded as generated files, and none ship in the zip. Next.js build manifests in `.next` did trigger the generic key rule. Development-only defaults are allowlisted in `.gitleaks.toml`.

**Bandit:** low-severity findings remain, mostly `assert` and subprocess notes. The gate fails at medium and above, and none remain.

**OWASP ZAP baseline:** a passive scan of the public frontend, run with `-I`, so warnings do not fail the gate. It reports 0 failures and some warnings. It did not test signed-in pages and it is not a penetration test. Warnings reviewed:
- `Cookie No HttpOnly`: `NEXT_LOCALE`, a language preference with no personal data. The session cookie is `httpOnly`.
- `CSP: style-src unsafe-inline`: accepted, since span overlays use inline styles. Scripts use nonces.
- `Cross-Origin-Embedder-Policy`: not set, since the app needs no cross-origin isolation.
- `Modern Web Application`: informational.
- Static file headers (`X-Content-Type-Options`, `Permissions-Policy`): fixed in `next.config.ts`. See `verification/security/zap-report.html` for the latest list.

ZAP warnings remaining in the latest run, also reviewed: `Content-Type Header Missing` is on 307 locale redirects with no body, and `CSP Header Not Set` is on 404 responses for `/robots.txt` and `/sitemap.xml`.
