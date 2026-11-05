# Product

## Problem
The same molecule at the same strength can cost very different amounts under different brands in India. Patients and caregivers struggle to read handwritten prescriptions, tell brand from generic names, find prices they can trust, find Jan Aushadhi options, and raise cheaper options with their doctor.

**Research status:** this comes from the brief and desk research. **No user research was done, and none is claimed.** Personas below are assumptions to test ([OPEN_ITEMS.md](OPEN_ITEMS.md)).

## Personas (assumptions)
- **Caregiver on a budget:** buys monthly medicines for a parent, uses a low-end Android phone, is comfortable in Hindi or Tamil.
- **Patient with a chronic condition:** repeat prescription, suspects a cheaper option exists, will not change without asking a doctor.
- **Community pharmacist:** can spot misread prescriptions, and wants a clear list and no liability for automated guesses.
- **Data steward (admin):** imports official lists and answers for their freshness.

## Jobs to be done
- When I have a prescription I cannot read, help me confirm what each medicine is, without guessing.
- When I know the medicine, show me what prices exist, what kind of price each is, and how old it is.
- When a cheaper option exists, show me exactly what differs, so I can ask my doctor.
- When I want Jan Aushadhi, show me listings and nearby Kendras without implying they have it.

## Competitor analysis
Verified 2026-11-05 from public pages unless noted. These are brief observations, not a feature audit.

| Service | What it is | Sells medicines? | Notes | Checked |
|---|---|---|---|---|
| [Tata 1mg](https://www.1mg.com/) | Online pharmacy, labs, consultations | Yes | Home page shows list and discounted prices | Page fetched 2026-11-05 |
| [PharmEasy](https://pharmeasy.in/) | Online pharmacy, labs, consultations | Yes | Takes prescription uploads to fulfil orders | Page fetched 2026-11-05 |
| [Apollo 24\|7](https://www.apollo247.com/) | Consultations, labs, pharmacy | Yes | Linked to Apollo Pharmacy | Page fetched 2026-11-05 |
| [Truemeds](https://www.truemeds.in/) | Online pharmacy (per its public positioning) | Believed yes | **Not verified:** the site returned 403 to our fetch | Attempted 2026-11-05 |
| NPPA Pharma Sahi Daam | Government price lookup app and site | No | Ceiling prices, same-composition brands, overcharge complaints; Hindi and English. [Secondary source](https://www.smartprix.com/bytes/are-you-paying-too-much-for-medicine-how-to-check-prices-with-pharma-sahi-daam/) | Search 2026-11-05 |
| Jan Aushadhi Sugam | Government app for Kendras and generics | No (locator) | Kendra finder, generic versus branded MRP comparison. [PIB](https://pib.gov.in/PressReleasePage.aspx?PRID=1583141) | Search 2026-11-05 |

Pharma Sahi Daam and Sugam are the closest in spirit, and both are official. **MediCompare does not have better data than Pharma Sahi Daam today.**

## Differentiation (design, not proven value)
1. **A human confirms identity before any comparison,** enforced on the server.
2. **Comparison refuses to compare unlike things,** and says why.
3. **Neutrality:** no selling, and ranking has no commercial input.
4. **Multilingual from the start,** including Tamil.
5. **A summary designed for the doctor conversation,** rather than a nudge to switch.

## User journeys
1. **Search:** type a name, including with a typo. See exact and possible matches. Open a record. See prices with type, source and date, then options and differences.
2. **Prescription:** consent, upload or type, wait for reading, compare with the image, confirm or correct each medicine, see prices for confirmed items, share a summary.
3. **Pharmacist review:** user chooses a pharmacist, pharmacist reviews and confirms, and the label shows who verified.
4. **Jan Aushadhi:** search by PIN or area, see listings and directory, contact the Kendra.
5. **Emergency:** any flow with emergency language is interrupted with 112.

## Requirements and acceptance
Feature requirements and acceptance criteria are as in the project brief, Section 5. How each is checked is in [TEST_PLAN.md](TEST_PLAN.md).

## Non-goals
Selling or dispensing, dosing or interaction advice, diagnosis, teleconsultation, emergency response, sponsored placement.
