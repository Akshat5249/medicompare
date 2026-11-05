# Resume bullets

All numbers come from `VERIFICATION_REPORT.md` and `docs/EVALUATION.md`. Keep the qualifiers, because without them the claims overstate the work. **Do not add users, savings or impact: there are none yet.** This project was built with substantial AI assistance (Claude Code). Be ready to say so, and be sure you can explain every part before you list it.

- Built MediCompare, a full-stack medicine price information app for India (FastAPI, PostgreSQL, Next.js, Docker), with a server-enforced gate that blocks price comparison until a person confirms each medicine, proven by 99 safety tests including direct API bypass attempts.
- Designed a deterministic medicine equivalence engine across ingredient, salt form, strength, dosage form, route and release type, and used property-based tests to show that unlike products are never compared per unit.
- Built an OCR pipeline with a pluggable engine interface and evaluated Tesseract against RapidOCR on 600 synthetic prescriptions on synthetic handwriting, which is easier than real prescriptions. Thresholds calibrated on validation data cut the false-match rate from 21.7% to 1.5% on the test split (1 of 67 suggestions, 95% upper bound 8.0%), at 17.4% coverage.
- Parsed official NPPA ceiling price lists and Authority minutes into a staged import pipeline with row-level provenance, including exact composition parsing: 352 real rows published and 38 sent to manual review rather than guessed.
- Automated 17 quality gates behind one command, including 295 backend tests (98.3% line coverage), 65 frontend tests (97.91%), 40 Playwright runs on two viewports with axe, and Trivy, Gitleaks and ZAP scans.
- Delivered English, Hindi and Tamil interfaces with search p95 of 530 ms at 57.7 requests/s and 0 errors in a local load test on the seeded 478-medicine catalogue.
