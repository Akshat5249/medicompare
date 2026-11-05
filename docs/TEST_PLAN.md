# Test plan

## Strategy
- **Safety and pricing logic** are pure functions, tested exhaustively with Hypothesis.
- **API tests** use real PostgreSQL, Redis and MinIO through FastAPI's test client, including direct calls that bypass the UI.
- **UI tests** use Vitest with a fake backend, for states and wording.
- **End-to-end tests** use Playwright against the running Docker stack on two viewports, with axe and video.
- **Failing tests are fixed at the cause.** Two real bugs were found this way during the build: partial words classed as exact matches, and a wrong exception type for invalid LLM output.

## Inventory
| Suite | File | Covers |
|---|---|---|
| Safety invariants | `backend/tests/test_safety_invariants.py` | Gate via API, look-alikes, IR vs MR, FDC, salt, strength, prompt injection, emergency, no stock wording, price labels |
| Properties | `backend/tests/test_properties.py` | Unlike products are never compared per unit; savings stay within one price type; staleness boundary; strength parser |
| Catalogue | `backend/tests/test_catalogue.py` | Typos, transliteration, strength and form separation, stale and no-price states, options, Jan Aushadhi, location privacy |
| Accounts and privacy | `backend/tests/test_accounts_privacy.py` | Sessions, lockout, CSRF, roles, consent, export, deletion of rows and objects, retention, rate limits |
| Pipeline | `backend/tests/test_pipeline.py` | Upload rejection, metadata stripping, pre-processing, both OCR engines, injection images and PDFs, LLM adapter |
| Portal and admin | `backend/tests/test_portal_admin.py` | Pharmacist access, share links with 410, summary content, import staging, review queue, importers, provenance |
| NPPA retail import | `backend/tests/test_nppa_retail.py` | Composition parsing from real rows, refusals, strength basis, release per ingredient, real-only mode |
| UI | `frontend/src/test/components.test.tsx` | All screens and states, translation completeness, no-stock wording, CSP |
| End-to-end | `frontend/e2e/main-flows.spec.ts` | Main flows and key failures; axe on every page |

The safety suite is run on its own with `make test-safety`, selected by the `safety` marker.

## Gates
Run all with `make verify`. Definitions and thresholds are in the [project's verification report](../VERIFICATION_REPORT.md).

| Gate | Command | Passes when |
|---|---|---|
| Lint | `make lint` | No errors |
| Types | `make types` | No errors |
| Backend | `make test-backend` | All pass; 85% overall and 95% on core modules |
| Safety | `make test-safety` | 100% pass |
| Frontend | `make test-frontend` | All pass; 80% lines |
| E2E and accessibility | `make e2e` | All pass; no serious or critical axe violations |
| Security | `make security`, `scripts/zap_baseline.sh` | No unjustified high or critical findings |
| Performance | `make perf` | Results recorded. No latency threshold was specified |
| Build | `docker compose up --wait`, `make smoke` | Healthy; smoke passes |
| Data | `make data-check` | All checks zero |
| Docs | `make docs-check` | Diagrams render, OpenAPI valid and current, links resolve |

## Known limits
- OCR accuracy assertions use clean rendered text. Accuracy is measured separately in [EVALUATION.md](EVALUATION.md).
- Emergency detection tests prove listed phrases only.
- Accessibility automation catches a subset of WCAG issues. No screen-reader session with a real user has been done.
- Load test runs client and server on one laptop.
- Low-end Android performance was not measured on a real device. Playwright's Pixel 7 profile only emulates viewport and touch.
