# Case study: MediCompare

## Problem
In India, the same molecule at the same strength can cost very different amounts by brand. People struggle to read prescriptions, tell brand from generic, trust a price, or find Jan Aushadhi options. A wrong "cheaper equivalent" is not just a bad result: it could harm someone.

**Research honesty:** this rests on desk research. No user research was done.

## The central decision
The interesting problem was not "OCR plus price lookup". It was: **how do you build this so it cannot confidently tell someone the wrong thing?** That led to three principles:
1. Software proposes, and a person decides.
2. Equal means provably equal. An unknown attribute never counts as a match.
3. Show what is true of the data, even when it makes the product look weaker.

## Key decisions
- **The gate takes no confidence score as input.** A score can change a label, never access. A database constraint backs this up.
- **Equivalence ignores names.** Look-alike names cannot produce a match, because names are not inputs.
- **An unstated salt form proves nothing.** NPPA does not state salts, so real ceiling prices rarely compare per unit. This makes the demo less impressive, and it is correct.
- **No savings across price types.** A ceiling price is a legal maximum, so a "saving" against it would be invented.
- **Respecting data terms.** The Jan Aushadhi portal requires permission to reproduce its data, so that data is not bundled, even though it was technically reachable.

## Architecture
A modular monolith: Next.js, FastAPI, PostgreSQL, Redis and RQ, private object storage, and OCR in a worker. Safety, matching and pricing are pure, strictly typed modules. See `docs/ARCHITECTURE.md`.

## Results (measured)
| Measure | Result |
|---|---|
| Verification gates passing | 17 of 17 |
| Backend tests and coverage | 236, 98.3% (core modules 97.3%) |
| Safety invariant tests | 96 |
| Frontend tests and coverage | 62, 97.89% |
| End-to-end runs with accessibility checks | 40 |
| Search latency, local load test | p50 66 ms, p95 200 ms, p99 250 ms |
| Catalogue | 253 real NPPA rows, 126 fictional demo rows |

### OCR, synthetic data only
| Test split | tesseract (selected) | rapidocr |
|---|---|---|
| Character error rate | 29.4% | 20.7% |
| Name F1 | 30.4% | 42.1% |
| Top candidate correct | 36.1% | 54.5% |
| False-match rate, no thresholds | 21.7% | 20.1% |
| False-match rate, calibrated | 1.5% (1/67) | 2.2% (2/91) |
| Coverage, calibrated | 17.4% | 23.4% |
| Latency per page, p50 | 1.04 s | 2.63 s |

**How to read this:** even on easy synthetic data, about one unfiltered top candidate in five is wrong, and at safe thresholds most lines get no suggestion. This is why people must confirm every medicine. The two false-match rates cannot be told apart at this sample size.

## What testing caught
- A partial word ("met") counted as an exact search match for both metformin and metoprolol.
- Demo accounts could never sign in, because validation rejects `.invalid` addresses.
- Rate limits would have treated all users as one address behind the proxy.
- `.venv` was being copied into images, more than doubling their size.
- A misconfigured Trivy command was silently scanning nothing.

## Limitations
No real brand or retail price data, so the core comparison runs on fictional data. No real handwriting evaluation, user research, pharmacist testing, native-language review or legal review. Not deployed. See `docs/OPEN_ITEMS.md`.

## What's next
1. Get brand data, or permission to use it. 2. Seek legal review, starting with medical device classification. 3. Run the consented real-data evaluation. 4. Test with pharmacists and patients.
