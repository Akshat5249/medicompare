# Open items

Everything here needs someone outside this build. Ordered by what most limits the product.

| # | Item | Why it matters | Exact next step |
|---|---|---|---|
| 1 | **Actual shop prices (MRPs)** | Real data is NPPA's legal maximums for part of the market. Actual shop prices are still fictional | License a commercial drug database, or collect printed MRPs with dates and a partner pharmacist. Import with the `catalogue` kind |
| 2 | **PMBJP permission** | Jan Aushadhi pages show only demo data | Email PMBI through the contact on janaushadhi.gov.in, asking for permission to reproduce the product list and Kendra directory, and for a machine-readable file. Then adapt the column mapping and run `python -m app.cli import` |
| 3 | **Real handwriting evaluation** | Results come from synthetic handwriting fonts and do not show real-world accuracy | Run the protocol in [EVALUATION.md](EVALUATION.md). Needs ethics review and consented data |
| 4 | **Legal review** | No compliance is claimed | Give [COMPLIANCE_NOTES.md](COMPLIANCE_NOTES.md) to an Indian health and privacy lawyer, starting with the medical-device question |
| 5 | **Pharmacist user testing** | The portal has not been used by a registered pharmacist, and no user research exists | Recruit 3 to 5 pharmacists and run the task script in [UX.md](UX.md) |
| 6 | **Clinical look-alike list** | The computed screen ([D10](DECISIONS.md)) can miss sound-alike pairs and flags harmless ones | License the ISMP/ECRI list, or commission a pharmacist-reviewed Indian list, and load it into `lasa_pairs` with `origin='clinical'` |
| 7 | **Native-speaker translation review** | Hindi and Tamil text was written by an AI and has not been reviewed. This matters most for the emergency and consent text | Review `frontend/messages/hi.json`, `frontend/messages/ta.json`, `data/sources/ingredient_aliases.csv` and the emergency phrases in `backend/app/safety/emergency.py` |
| 8 | **Salt form data for ceiling prices** | NPPA retail rows state salts, but ceiling price rows do not, so those cannot compare per unit ([D5](DECISIONS.md)) | Have a pharmacist curate salts from NLEM and the Gazette notifications, and import with citations |
| 9 | **CDSCO data** | Regulatory notices are demo only | Confirm reuse terms with CDSCO, then build a monthly NSQ parser against the real PDFs |
| 10 | **Current NPPA lists** | Loaded data says "As on March, 2026" | Rerun `download_nppa.sh` when NPPA updates its page, and consider parsing Gazette notifications |
| 11 | **More NPPA data** | Only 5 ceiling categories and 4 sets of minutes are loaded. 23 older minutes are scans | Parse the current consolidated list. Enter the scanned minutes by hand with a second check, or ask NPPA for text versions |
| 11a | **NPPA retail review queue** | 25 real rows are unpublished, including combination kits | Review them on the admin page with a pharmacist. Check published rows against Gazette notifications |
| 12 | **Live deployment** | Nothing is deployed and there is no live URL | Follow [DEPLOYMENT.md](DEPLOYMENT.md). Needs a domain and a hosting account |
| 13 | **GitHub Actions run** | `ci.yml` has never run on GitHub | Push to a repository, check the run, then add the status badge to the README |
| 14 | **TrOCR evaluation** | A handwriting-specific model may beat both tested engines | Add an `OcrEngine` adapter and rerun `make evaluate` on a machine with enough memory |
| 15 | **Optional LLM adapter** | Tested only with a fake client, never against the live API, and not wired into the pipeline | Set `LLM_API_KEY`, test on synthetic data, and evaluate before enabling |
| 16 | **Translated server text** | Match reasons, difference reasons and error titles from the API are in English on all locales | Return codes from the API and translate them in the UI |
| 17 | **Penetration test** | Scans are not a substitute | Commission one before handling real data |
