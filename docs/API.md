# API

Versioned at `/api/v1`. The OpenAPI 3.1 spec is generated from code and committed as [openapi.yaml](openapi.yaml). Interactive docs run at `/api/v1/docs`. A Bruno collection is in [`docs/api-collection`](api-collection/README.md).

## Conventions
- **Errors:** RFC 9457 `application/problem+json`, with a stable `code`:
  ```json
  {"type": "https://medicompare.invalid/problems/item_not_verified", "title": "This medicine has not been verified",
   "status": 409, "code": "item_not_verified", "item_status": "needs_verification"}
  ```
- **Auth:** session cookie set by login, register or guest.
- **CSRF:** state changes need `X-CSRF-Token` with the value from `/auth/me`, login or register.
- **Rate limits:** public 300/min, auth 20/min, upload 30/hour, per address. Exceeding returns `429 rate_limited`.

## Endpoints
| Method and path | Access | Purpose |
|---|---|---|
| `GET /health/live`, `/health/ready` | Public | Liveness; readiness checks the database, Redis and storage |
| `GET /search?q=` | Public | Exact and possible matches with reasons; emergency interrupt |
| `GET /medicines/{id}` | Public | Composition, source, flags |
| `GET /medicines/{id}/prices` | Public | Prices with type, source, date, staleness |
| `GET /medicines/{id}/options` | Public | Equivalents, not-comparable products, Jan Aushadhi listings |
| `POST /safety/check` | Public | Emergency detection for free text |
| `GET /jan-aushadhi/products`, `/kendras` | Public | Listings; directory by `pin`, `area` or `lat`+`lon` |
| `GET /shared/{token}`, `/shared/{token}/pdf` | Link | Summary. `410` when expired or revoked |
| `POST /auth/register`, `/register-pharmacist`, `/login`, `/guest`, `/logout` · `GET /auth/me` | Public / session | Accounts |
| `GET,POST /lists` · `POST /lists/{id}/items` · `DELETE /lists/{id}` | Account | Saved lists |
| `GET /me/export` · `DELETE /me` | Session | JSON export; delete account |
| `GET /prescriptions/consent-notice` | Public | What is processed, by what, where, for how long |
| `POST /prescriptions/upload` · `/manual` | Session + CSRF | Intake |
| `GET /prescriptions` · `/{id}` · `/{id}/pages/{n}` | Owner | History, status with items, private image |
| `PATCH /prescriptions/{id}/items/{item}` | Owner + CSRF | Correct text. Clears verification and rematches |
| `POST .../items/{item}/verify` · `/reject` · `/unresolved` | Owner + CSRF | Human decisions |
| `GET .../items/{item}/prices` · `/options` | Owner, **verified items only** | **The gate.** Otherwise `409 item_not_verified` |
| `DELETE /prescriptions/{id}` | Owner + CSRF | Removes rows and objects |
| `GET /prescriptions/{id}/summary`, `/summary.pdf` · `POST,DELETE .../share-links` | Owner | Summaries and links |
| `GET /pharmacists` · `POST,DELETE /prescriptions/{id}/shares` | Session | Choose or remove a pharmacist |
| `GET /pharmacist/queue` · `/pharmacist/prescriptions/{id}` · `/pages/{n}` | Approved pharmacist, shared only | Review |
| `PATCH,POST /pharmacist/prescriptions/{id}/items/{item}` · `/verify` · `/unresolved` · `POST .../complete` | Approved pharmacist + CSRF | Pharmacist decisions |
| `GET /admin/sources`, `/imports`, `/review-queue`, `/pharmacists`, `/audit` | Admin | Dashboards |
| `POST /admin/imports` · `/{id}/publish` · `/{id}/reject` | Admin + CSRF | Staging and publication |
| `PUT,DELETE /admin/review-queue/{row}` · `POST /admin/pharmacists/{id}/decision` | Admin + CSRF | Corrections and approvals |

## Main error codes
`unauthenticated`, `forbidden`, `csrf_failed`, `bad_origin`, `rate_limited`, `account_locked`, `consent_required`, `unsupported_type`, `file_too_large`, `corrupt_file`, `too_many_pages`, `item_not_verified`, `not_a_candidate`, `lasa_review_required`, `strength_conflict`, `nothing_verified`, `link_expired`, `pharmacist_not_approved`.

## Note on public medicine routes
`/medicines/{id}/prices` is a catalogue lookup that any visitor can call with any id. It asserts nothing about a prescription. The gate protects the link from a prescription item to prices. It cannot stop someone opening a record they chose themselves, and the UI never carries an unverified identity into those pages.
