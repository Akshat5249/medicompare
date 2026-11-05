# Decision log

Each entry records the context, the options, the choice and why. Dates are 2026-11-05 unless stated.

## D1. MinIO image source
- **Context:** `minio/minio` on Docker Hub and `quay.io/minio/minio` both refused pulls from this environment (pull access denied; HTTP 401).
- **Options:** switch to SeaweedFS or RustFS; use another MinIO build.
- **Choice:** `cgr.dev/chainguard/minio`, tested at `RELEASE.2026-10-23T20-06-51Z`.
- **Why:** the brief names MinIO, and this keeps it. The free Chainguard tag only offers `latest`, so production should pin a digest. The image has no shell, so Compose has no MinIO healthcheck; `Storage.ensure_bucket` and `/health/ready` cover readiness.

## D2. Backend tests run in a container
- **Context:** `brew install tesseract` failed on this Mac (Homebrew reports no usable compiler in its Tier 3 configuration).
- **Choice:** `backend/Dockerfile.test` provides Python 3.12, dev tools and Tesseract. `make test-backend` uses it.
- **Why:** no changes to the host toolchain, and CI and local runs match.

## D3. OCR engines evaluated
- **Options:** Tesseract, PaddleOCR, TrOCR, cloud APIs.
- **Choice:** Tesseract and RapidOCR. RapidOCR runs the PP-OCR models (the PaddleOCR family) on ONNX Runtime.
- **Why:** both run on CPU in a small image. TrOCR needs PyTorch and substantial memory, which conflicts with the low-cost target, so it was **not evaluated**. The `OcrEngine` protocol makes it a small addition. See [EVALUATION.md](EVALUATION.md).

## D4. Whole-word rule for exact search matches
- **Context:** a test found "amlodipin" classed as exact because the text appears inside the name.
- **Choice:** exact matches need whole words. Everything else is a possible match with a warning.
- **Why:** "met" must never be an exact match for both metformin and metoprolol.

## D5. An unstated salt form proves nothing
- **Context:** NPPA lists "Metformin", not "Metformin hydrochloride".
- **Options:** treat two blanks as equal; infer the usual salt; treat blank as not provable.
- **Choice:** not provable. The product appears under "Not directly comparable" with the reason.
- **Why:** the brief requires a salt-form match and forbids inference. The cost is real: NPPA ceiling prices rarely compare per unit against branded products until salt data exists. The ceiling price is still shown on its own record.

## D6. Savings only within one price type
- **Choice:** ceiling versus MRP never produces a saving figure.
- **Why:** a ceiling price is a legal maximum, not what anyone pays, so a "saving" against it would be invented.

## D7. Guest sessions
- **Context:** accounts are only required for saved lists, history and pharmacist sharing, but prescription rows need an owner.
- **Choice:** a guest is a `users` row with no email, removed by the retention job.
- **Why:** one authorization path for everyone, with no special cases at the gate.

## D8. Prescription images are served through the API, not signed URLs
- **Context:** the stack table suggests short-lived signed URLs. Signed URLs would expose the storage host, and anyone holding one can read the image until it expires.
- **Choice:** the bucket stays private and `/prescriptions/{id}/pages/{n}` streams bytes after an ownership or share check, with `no-store`.
- **Why:** access can be revoked instantly. This is a deliberate deviation from the brief.

## D9. Sanitised originals
- **Context:** the brief asks to both preserve the original and strip EXIF.
- **Choice:** the stored original is a pixel-identical re-encode (PNG, after applying orientation) or a PDF with metadata, named objects and open actions removed. Processed pages are stored separately.
- **Why:** GPS data never reaches storage. The exact uploaded bytes are not kept.

## D10. Computed look-alike screen instead of a clinical list
- **Context:** the ISMP confused-names list has moved to ECRI and is copyrighted. No official Indian list with reuse terms was found.
- **Choice:** Jaro-Winkler screen over catalogue brands and ingredients at 0.88. A hit only adds friction.
- **Why:** copying a list without a licence is not acceptable, and inventing "clinical" pairs would be fabrication. This is weaker than a clinical list; see [OPEN_ITEMS.md](OPEN_ITEMS.md).

## D11. Client-side data fetching
- **Choice:** pages fetch through one `useApi` hook with shared loading and error states, through a same-origin rewrite.
- **Why:** uniform states and simple cookies and CSRF. The cost is that first paint has no data. The JS payload per route is about 130 kB.

## D12. English-only PDF
- **Context:** ReportLab cannot shape Indic scripts, and WeasyPrint needs system libraries in every image.
- **Choice:** summary PDFs are in English; the web summary is translated and printable.

## D13. Database hard deletes
- **Choice:** prescriptions and accounts are hard-deleted, with objects removed first. Audit rows lose the actor link through `ON DELETE SET NULL`.
- **Why:** the brief's deletion guarantee. Catalogue rows are never deleted by users, and prices are append-only observations.

## D14. No Git commits by the build
- **Context:** the build environment's rule is to commit only when the user asks.
- **Choice:** the repository is delivered as a tree without history. Pre-commit and CI configuration are included, and Gitleaks scans the directory.

## D15. RQ with a simple scheduler loop
- **Options:** Celery, Arq, RQ.
- **Choice:** RQ `SimpleWorker` keeps the OCR model loaded between jobs, and a small `worker/scheduler.py` runs retention hourly.
- **Why:** least machinery for two job types.

## D16. Rate limiting behaviour when Redis fails
- **Choice:** public reads fail open; login, registration and upload fail closed.
- **Why:** a Redis outage should not take down public price information, and should not remove brute-force protection.

## D17. NPPA staleness cadence of 90 days
- **Context:** the lists are marked "As on March, 2026". NPPA revises ceiling prices annually from 1 April and notifies changes through the year, so this copy is probably superseded.
- **Choice:** 90 days, so these real prices currently show "May be out of date".
- **Why:** this is what the data honestly warrants today.

## D18. Default OCR engine
- **Context:** the rule set before scoring was lowest validation false-match rate, then highest coverage. Tesseract won narrowly. RapidOCR reads text better, but the false-match difference is within noise.
- **Choice:** keep the rule, so Tesseract is the default. Thresholds only apply to the engine they were measured on; any other engine shows "not calibrated".
- **Why:** changing the rule after seeing results would make the selection meaningless. Tesseract is also faster on CPU and cheaper to run. RapidOCR stays available through `OCR_ENGINE`. Better data should revisit this.

## D19. Licence
- **Choice:** MIT for the code, as a common default for a portfolio repository. Data and fonts keep their own terms, as noted in `LICENSE`.
- **Note:** this is easy for the owner to change before publishing.

## D20. Rate limits use the forwarded client address
- **Context:** requests reach the backend through the Next.js rewrite, so `request.client` was always the frontend container, and per-address limits would have applied to all users together. Found by review before E2E.
- **Choice:** `uvicorn --proxy-headers --forwarded-allow-ips=*`.
- **Why it is safe:** in production the backend has no published port, and Caddy overwrites `X-Forwarded-For` by default. In local development the header can be spoofed, which does not matter there. **If you change the proxy, keep this property.**
- **Test runs:** E2E and load traffic comes from one address, so `verify.sh` raises the limits through environment variables. Unit tests prove the limit works.

## D21. Image size and runtime images
- **Context:** the root build context had no `.dockerignore`, so `.venv` was copied into images, a `chown` layer then duplicated it, and each build sent the evaluation images and `node_modules` as context. Docker usage reached about 50 GB on the build machine. Trivy also flagged build tools and npm in runtime images.
- **Choice:** a root `.dockerignore`, `COPY --chown` instead of a recursive `chown`, no `uv` or `setuptools` at runtime, and `cgr.dev/chainguard/node` for the frontend runtime (no shell, npm or root user).
- **Effect (measured):** backend image 3.33 GB to 1.45 GB as Docker reports it; contents 1.6 GB to 913 MB.
- **Trade-offs:** the build uses Node 22 and the runtime is Chainguard's current Node, since the free tag is `latest` only. E2E tests run against this pairing. Pin a digest in production. `gcr.io/distroless/nodejs22-debian12` was tried and rejected: its OpenSSL was unpatched when scanned.
