# Compliance notes

**This is not legal advice, and no compliance is claimed.** It maps open questions for a lawyer. Sources were accessed 2026-11-05. Most are secondary, because primary Gazette documents were not retrieved; each must be checked against the primary text.

## Digital Personal Data Protection Act 2023 and Rules 2025
- **May apply:** MediCompare would be a data fiduciary for account and prescription data. Reports say the Rules were notified in November 2025 (G.S.R. 846(E) is cited) with phased commencement, and the main consent, breach and children's-data duties arriving around May 2027. ([S.S. Rana](https://ssrana.in/articles/meity-notifies-final-digital-personal-data-protection-rules-2025/), [Mondaq](https://www.mondaq.com/india/data-protection/1708434/operationalising-indias-data-protection-regime-analysing-the-newly-notified-dpdp-rules-2025))
- **Design effect:** explicit versioned consent before upload, data minimisation (redaction, guest use), erasure and export, a short retention default.
- **For legal review:** exact commencement dates; notice content and languages; breach notification mechanics; whether a guest is a data principal we can notify; children's data, since a parent may upload a child's prescription; any Significant Data Fiduciary exposure; cross-border transfer if hosted outside India.

## Information Technology Act 2000 and SPDI Rules 2011
- **May apply:** "medical records and history" are sensitive personal data under the 2011 Rules, and intermediary obligations may apply to user uploads and share links.
- **Design effect:** encryption expectations in [SECURITY_PRIVACY.md](SECURITY_PRIVACY.md), audit logging, a grievance contact to be added before launch.
- **For legal review:** how the 2011 Rules interact with DPDP as it commences; whether a grievance officer is needed.

## Drugs and Cosmetics Act 1940 and Rules 1945 (online pharmacy scope)
- **May apply:** draft e-pharmacy rules from 2018 are reported as not yet final, and regulators have challenged unlicensed online sale. ([LSHTM report](https://www.lshtm.ac.uk/media/102426), [Business Standard](https://www.business-standard.com/india-news/parliamentary-panel-seeks-implementation-of-e-pharmacy-rules-soon-123032800877_1.html))
- **Design effect:** no sale, order, cart, delivery or stock. Copy avoids stock wording, enforced by tests. Schedule flags are display-only.
- **For legal review:** whether reading prescriptions and showing options could be treated as facilitating sale, and whether any pharmacy partnership would change that. The product has none.

## Generic prescribing and substitution
- **May apply:** NMC's 2023 conduct regulations (which required generic names) were [held in abeyance](https://www.tribuneindia.com/news/nation/nmc-puts-generic-drugs-order-on-hold-538003) shortly after notification, with the 2002 regulations reportedly applying meanwhile. We found no later change, but this may be out of date. Pharmacist substitution law was **not established** by our search.
- **Design effect:** alternatives are "options to discuss", never recommendations. The summary is addressed to a doctor or pharmacist.
- **For legal review:** when a pharmacist may substitute; the status of the 2023 regulations; whether pharmacist notes in the portal are professional advice, with what liability.

## Drug advertising
- **May apply:** Drugs and Magic Remedies (Objectionable Advertisements) Act 1954, Rule 106 of the Drugs Rules, and restrictions on promoting prescription medicines.
- **Design effect:** no sponsorship, no promotional claims, no ranking influence.
- **For legal review:** whether displaying brand names and comparative prices could be read as advertising. NPPA and PMBI publish similar information, but that does not settle the question.

## Medical device classification
- **May apply:** Medical Devices Rules 2017. CDSCO issued draft guidance on medical device software in [October 2025](https://india-briefing.com/news/cdsco-draft-guidance-medical-software-40691.html) and [final guidance is reported in 2026](https://www.emergobyul.com/news/india-cdsco-finalizes-guidance-medical-device-software). The final text was not reviewed.
- **Design effect:** intended use is stated as information only, with no diagnosis, dosing or treatment recommendation. OCR output is never decisive: a human confirms every item.
- **For legal review (highest priority):** whether prescription reading plus "equivalent product" display is medical device software under the final guidance, and at what class. Adding dosing, interaction or automatic matching would raise this risk, and is out of scope.

## Data reuse
- **NPPA:** reuse permitted with accuracy and acknowledgement. Commercial use should be confirmed.
- **PMBJP:** permission needed before reproduction.
- **CDSCO:** terms not confirmed. See [DATA_SOURCES.md](DATA_SOURCES.md).

## Other sources for review
[Cyril Amarchand on medical device software](https://corporate.cyrilamarchandblogs.com/2026/01/medical-device-as-software-has-cdsco-guidance-changed-the-rules/), [Nishith Desai on the draft guidance](https://www.nishithdesai.com/research-and-articles/hotline/pharma-healthcare-update/the-next-frontier-in-medtech-regulation-dissecting-cdscos-draft-guidance-on-medical-device-software-15465).
