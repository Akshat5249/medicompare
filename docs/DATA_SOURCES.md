# Data sources

Investigated 2026-11-05 from this build environment. **Bottom line: one official source is loaded as real data. Brand products, shop prices, Jan Aushadhi data and regulatory notices are flagged demo data until the steps below are done.**

| Source | Classification | In this build |
|---|---|---|
| NPPA therapeutic-category ceiling lists | **Available, reuse permitted** | **Real: 253 rows published, 13 in review queue** |
| NPPA Compendium of Prices 2022 | Available, reuse permitted | Not loaded: prices dated 2022 |
| NPPA Pharma Sahi Daam search | Available as an interactive tool | Not used: no bulk export found, no scraping |
| PMBJP product list and Kendra directory | **Restricted: permission required** | Demo data, importer ready |
| CDSCO NSQ alerts, prohibited FDCs | Reachable, terms not confirmed | Demo data, importer ready |
| NLEM | Not separately loaded | Covered indirectly by NPPA's scheduled formulations |
| data.gov.in Kendra datasets | Reachable, counts only | Not used: state-level counts, not addresses |
| Brand catalogue and retail MRPs | **No official open source found** | Demo data only |

## NPPA ceiling prices (real data)
- **Owner:** National Pharmaceutical Pricing Authority, Department of Pharmaceuticals, Government of India.
- **URL:** https://nppa.gov.in/en/therapeuticcategorywiseceilingpricelist
- **Access:** public PDFs, downloaded by [`data/importers/download_nppa.sh`](../data/importers/download_nppa.sh) and parsed by [`data/importers/nppa_pdf.py`](../data/importers/nppa_pdf.py).
- **Licence:** NPPA's copyright policy (https://nppa.gov.in/en/copyrightpolicy) allows free reproduction in any format when accurate, not misleading and acknowledged. Third-party material is excluded.
- **Commercial use:** the policy does not separately restrict it, but this needs [legal review](OPEN_ITEMS.md).
- **Cadence:** annual WPI revision from 1 April, plus notifications during the year. Stored as 90 days ([D17](DECISIONS.md)).
- **Fields:** molecule, dosage form, strength, unit, ceiling price in rupees. Price type: `ceiling`.
- **Gaps:** five categories only (anti-cancer, anti-diabetes, anti-HIV, anti-TB, cardiovascular), so common medicines such as paracetamol have no real row here. No salt forms, no brands, no manufacturers. Files say "As on March, 2026".
- **Authority caveat:** NPPA states that its lists do not replace the Gazette notifications, which remain the official version.
- **Verified:** 2026-11-05. SHA-256 of each PDF is printed by the download script and stored per batch.

### Parse results
267 rows were read. 253 are published. 14 did not publish:
- 13 fail validation with a stated reason (for example `10000KU`, `(As licensed)`, or one row listing several release types) and wait in the admin review queue.
- 1 further row could not be parsed from the PDF at all and is listed in `data/sources/nppa_parse_failures.csv`.

## PMBJP / Jan Aushadhi
- **Owner:** Pharmaceuticals & Medical Devices Bureau of India (PMBI), Department of Pharmaceuticals.
- **URL:** https://janaushadhi.gov.in
- **Access:** a JavaScript application backed by a private API. Older direct PDF paths now return the application shell.
- **Licence:** the portal's copyright text says material may be reproduced free of charge **after taking permission by email**.
- **Decision:** the private API was not called and no data was copied. Bundling it without permission would breach the stated terms.
- **To complete:** see [OPEN_ITEMS.md](OPEN_ITEMS.md). Load with `python -m app.cli import <source> ja_products <file>`.
- **Importer columns:** `drug_code, generic_name, group_name, unit_size, mrp, observed_at`, and `kendra_code, name, address, district, state, pin_code, latitude, longitude, observed_at`. **These are modelled on what the portal displays, and the official file format was not seen.** Expect to adapt the column mapping when real files arrive.
- **Price type:** catalogue. **Availability:** the directory says nothing about what a Kendra has.

## CDSCO
- **Owner:** Central Drugs Standard Control Organisation.
- **URLs:** https://cdsco.gov.in/opencms/opencms/en/Notifications/Alerts/ (reachable; some paths returned 403 to scripted requests).
- **Contents:** monthly not-of-standard-quality alerts, spurious drug lists, prohibited FDC notifications, schedule classifications.
- **Licence:** reuse terms were not confirmed, so nothing was bundled.
- **Importer:** `regulatory_flags` takes `medicine_display_name, flag_type, description, source_url, source_date`. Alerts are batch-specific, so a real importer must keep the batch and manufacturer in `description` and must not imply that every batch is affected.
- **Gap:** NSQ alerts name brands and batches. Matching them to catalogue rows needs a brand catalogue this build does not have.

## data.gov.in
- **URL:** https://data.gov.in/resources/stateut-wise-janaushadhi-kendras-opened-under-pradhan-mantri-bhartiya-janaushadhi
- **Contents:** state-wise counts of Kendras, not addresses, so it cannot power a locator. Each resource's licence must be checked individually.

## Demo dataset
- **Files:** `data/demo/`, produced by a seeded script ([`build_demo.py`](../data/demo/build_demo.py)).
- **Everything is fictional:** brand names (all start with "Demo"), manufacturers, prices, Kendras, product codes and regulatory notices.
- **Controls:** demo sources have `is_demo=true`, the flag is copied to every row, a data-quality check fails on mismatch or unprefixed demo brands, and the UI shows a "Demo data" badge.

## Ingredient aliases
`data/sources/ingredient_aliases.csv` holds Hindi and Tamil spellings written for search recall only. They never affect equivalence and need [native-speaker review](OPEN_ITEMS.md).
