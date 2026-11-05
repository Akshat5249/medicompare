#!/usr/bin/env python3
"""Generate portfolio documents and report.pdf from measured results, so numbers cannot drift.

Inputs: verification/logs, verification/perf, verification/coverage-backend.json,
frontend/coverage/coverage-summary.json, evaluation/results/results.json.
Output: verification/metrics.json and the files in portfolio/.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    CondPageBreak,
    Image,
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "portfolio"
LOGS = ROOT / "verification/logs"


def log(name: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", (LOGS / f"{name}.log").read_text(errors="replace"))


def last(pattern: str, text: str) -> str:
    return re.findall(pattern, text)[-1]


def published_counts() -> tuple[int, int, int]:
    """Published rows and review-queue size, from the same validators the import uses."""
    import sys

    sys.path.insert(0, str(ROOT / "backend"))
    from app.imports.normalize import normalize_nppa_retail_row, normalize_nppa_row

    def run(name: str, normalize) -> tuple[int, int]:
        with open(ROOT / "data/sources" / name, encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        seen = {normalize(row)[0]["display_name"] + str(normalize(row)[0]["observed_at"]) + normalize(row)[0]["release_type"] for row in rows if normalize(row)[0]}
        return len(seen), len(rows) - len(seen)

    ceiling, ceiling_queue = run("nppa_ceiling_prices.csv", normalize_nppa_row)
    retail, retail_queue = run("nppa_retail_raw.csv", normalize_nppa_retail_row)
    return ceiling, retail, ceiling_queue + retail_queue


def metrics() -> dict:
    ceiling_ok, retail_ok, queue = published_counts()
    evaluation = json.loads((ROOT / "evaluation/results/results.json").read_text())
    chosen = evaluation["selected_engine"]
    other = next(e for e in evaluation["engines"] if e != chosen)
    perf = {row["Name"]: row for row in csv.DictReader((ROOT / "verification/perf/locust_stats.csv").open())}
    gates = [line.split("\t")[:2] for line in (ROOT / "verification/gate_status.tsv").read_text().splitlines()]
    return {
        "backend_tests": int(last(r"(\d+) passed", log("backend_tests"))),
        "backend_coverage": round(json.loads((ROOT / "verification/coverage-backend.json").read_text())["totals"]["percent_covered"], 1),
        "core_coverage": float(last(r"core modules: ([\d.]+)%", log("backend_tests"))),
        "safety_tests": int(last(r"(\d+) passed", log("safety_suite"))),
        "frontend_tests": int(last(r"Tests\s+(\d+) passed", log("frontend_tests"))),
        "frontend_coverage": json.loads((ROOT / "frontend/coverage/coverage-summary.json").read_text())["total"]["lines"]["pct"],
        "e2e_tests": int(last(r"(\d+) passed", log("e2e_accessibility"))),
        "gates_total": len(gates),
        "gates_passed": sum(result == "PASS" for _, result in gates),
        "search_p50": int(perf["search"]["50%"]),
        "search_p95": int(perf["search"]["95%"]),
        "search_p99": int(perf["search"]["99%"]),
        "comparison_p95": int(perf["comparison"]["95%"]),
        "perf_requests": int(perf["Aggregated"]["Request Count"]),
        "perf_failures": int(perf["Aggregated"]["Failure Count"]),
        "perf_rps": round(float(perf["Aggregated"]["Requests/s"]), 1),
        "catalogue_real": ceiling_ok + retail_ok,
        "catalogue_ceiling": ceiling_ok,
        "catalogue_retail": retail_ok,
        "catalogue_demo": 126,
        "review_queue": queue,
        "images": 600,
        "selected_engine": chosen,
        "other_engine": other,
        "engines": {
            engine: {
                "cer": round(data["test"]["cer"] * 100, 1),
                "wer": round(data["test"]["wer"] * 100, 1),
                "f1": round(data["test"]["entity_f1"] * 100, 1),
                "top1": round(data["test"]["exact_match_accuracy_top1"] * 100, 1),
                "p50_s": round(data["test"]["latency_ms_p50"] / 1000, 2),
                "unfiltered_fmr": round(data["test"]["uncalibrated"]["false_match_rate"] * 100, 1),
                "suggested": data["calibrated_test"]["suggested"],
                "false_matches": data["calibrated_test"]["false_matches"],
                "fmr": round(data["calibrated_test"]["false_match_rate"] * 100, 1),
                "fmr_upper": round(data["calibrated_test"]["false_match_rate_upper_95"] * 100, 1),
                "coverage": round(data["calibrated_test"]["coverage_of_identifiable_lines"] * 100, 1),
                "abstention": round(data["calibrated_test"]["abstention_rate"] * 100, 1),
            }
            for engine, data in evaluation["engines"].items()
        },
    }


def write_markdown(m: dict) -> None:
    s = m["engines"][m["selected_engine"]]
    o = m["engines"][m["other_engine"]]
    caveat = "on synthetic handwriting, which is easier than real prescriptions"
    (OUT / "RESUME_BULLETS.md").write_text(f"""# Resume bullets

All numbers come from `VERIFICATION_REPORT.md` and `docs/EVALUATION.md`. Keep the qualifiers, because without them the claims overstate the work. **Do not add users, savings or impact: there are none yet.** This project was built with substantial AI assistance (Claude Code). Be ready to say so, and be sure you can explain every part before you list it.

- Built MediCompare, a full-stack medicine price information app for India (FastAPI, PostgreSQL, Next.js, Docker), with a server-enforced gate that blocks price comparison until a person confirms each medicine, proven by {m['safety_tests']} safety tests including direct API bypass attempts.
- Designed a deterministic medicine equivalence engine across ingredient, salt form, strength, dosage form, route and release type, and used property-based tests to show that unlike products are never compared per unit.
- Built an OCR pipeline with a pluggable engine interface and evaluated Tesseract against RapidOCR on {m['images']} synthetic prescriptions {caveat}. Thresholds calibrated on validation data cut the false-match rate from {s['unfiltered_fmr']}% to {s['fmr']}% on the test split ({s['false_matches']} of {s['suggested']} suggestions, 95% upper bound {s['fmr_upper']}%), at {s['coverage']}% coverage.
- Parsed official NPPA ceiling price lists and Authority minutes into a staged import pipeline with row-level provenance, including exact composition parsing: {m['catalogue_real']} real rows published and {m['review_queue']} sent to manual review rather than guessed.
- Automated {m['gates_total']} quality gates behind one command, including {m['backend_tests']} backend tests ({m['backend_coverage']}% line coverage), {m['frontend_tests']} frontend tests ({m['frontend_coverage']}%), {m['e2e_tests']} Playwright runs on two viewports with axe, and Trivy, Gitleaks and ZAP scans.
- Delivered English, Hindi and Tamil interfaces with search p95 of {m['search_p95']} ms at {m['perf_rps']} requests/s and 0 errors in a local load test on the seeded {m['catalogue_real'] + m['catalogue_demo']}-medicine catalogue.
""")
    (OUT / "CASE_STUDY.md").write_text(f"""# Case study: MediCompare

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
- **An unstated salt form proves nothing.** NPPA's ceiling lists do not state salts, so those rows rarely compare per unit. This makes the demo less impressive, and it is correct.
- **No OCR on official prices.** Most NPPA minutes are scans. Reading them with OCR could turn a misread digit into an "official" price, so they were left out.
- **No savings across price types.** A ceiling price is a legal maximum, so a "saving" against it would be invented.
- **Respecting data terms.** The Jan Aushadhi portal requires permission to reproduce its data, so that data is not bundled, even though it was technically reachable.

## Architecture
A modular monolith: Next.js, FastAPI, PostgreSQL, Redis and RQ, private object storage, and OCR in a worker. Safety, matching and pricing are pure, strictly typed modules. See `docs/ARCHITECTURE.md`.

## Results (measured)
| Measure | Result |
|---|---|
| Verification gates passing | {m['gates_passed']} of {m['gates_total']} |
| Backend tests and coverage | {m['backend_tests']}, {m['backend_coverage']}% (core modules {m['core_coverage']}%) |
| Safety invariant tests | {m['safety_tests']} |
| Frontend tests and coverage | {m['frontend_tests']}, {m['frontend_coverage']}% |
| End-to-end runs with accessibility checks | {m['e2e_tests']} |
| Search latency, local load test | p50 {m['search_p50']} ms, p95 {m['search_p95']} ms, p99 {m['search_p99']} ms |
| Catalogue | {m['catalogue_real']} real NPPA rows ({m['catalogue_ceiling']} ceiling, {m['catalogue_retail']} notified retail), {m['catalogue_demo']} fictional demo rows |

### OCR, synthetic data only
| Test split | {m['selected_engine']} (selected) | {m['other_engine']} |
|---|---|---|
| Character error rate | {s['cer']}% | {o['cer']}% |
| Name F1 | {s['f1']}% | {o['f1']}% |
| Top candidate correct | {s['top1']}% | {o['top1']}% |
| False-match rate, no thresholds | {s['unfiltered_fmr']}% | {o['unfiltered_fmr']}% |
| False-match rate, calibrated | {s['fmr']}% ({s['false_matches']}/{s['suggested']}) | {o['fmr']}% ({o['false_matches']}/{o['suggested']}) |
| Coverage, calibrated | {s['coverage']}% | {o['coverage']}% |
| Latency per page, p50 | {s['p50_s']} s | {o['p50_s']} s |

**How to read this:** even on easy synthetic data, about one unfiltered top candidate in five is wrong, and at safe thresholds most lines get no suggestion. This is why people must confirm every medicine. The two false-match rates cannot be told apart at this sample size.

## What testing caught
- A partial word ("met") counted as an exact search match for both metformin and metoprolol.
- Demo accounts could never sign in, because validation rejects `.invalid` addresses.
- Rate limits would have treated all users as one address behind the proxy.
- `.venv` was being copied into images, more than doubling their size.
- A misconfigured Trivy command was silently scanning nothing.
- Reading real NPPA data, a preservative's note silently dropped moxifloxacin from an eye drop's composition.

## Limitations
No real shop prices: real data is NPPA's legal maximums for part of the market. No real handwriting evaluation, user research, pharmacist testing, native-language review or legal review. Not deployed. See `docs/OPEN_ITEMS.md`.

## What's next
1. Get brand data, or permission to use it. 2. Seek legal review, starting with medical device classification. 3. Run the consented real-data evaluation. 4. Test with pharmacists and patients.
""")
    (OUT / "DEMO_SCRIPT.md").write_text(f"""# Demo script

Setup: `make up`, then open http://localhost:3000. Say early that brands and shop prices are fictional demo data.

## 60-second pitch
The same medicine can cost very different amounts by brand in India, but a wrong "cheaper equivalent" could hurt someone. MediCompare is a neutral price information tool built around that risk. It reads a prescription, but a person must confirm every medicine before the server will show a single price. It only compares products proven identical on ingredient, salt, strength, form, route and release type, and every price shows its type, source and date. Real government price limits are loaded, naming real companies, and actual shop prices are the main gap. It is a working, tested prototype with {m['safety_tests']} safety tests, not yet a live service.

## 3-minute walkthrough
| Time | Do | Say |
|---|---|---|
| 0:00 | Home page | "Information only, and it sells nothing. Note the notice on every page" |
| 0:20 | Search `metformn` | "Typo tolerated, but these are only possible matches, and it says why" |
| 0:40 | Open `Metformin 500mg Tablet` | "Real NPPA data. It's labelled as a legal maximum, not a shop price, and flagged as possibly out of date, because it is" |
| 1:00 | Scroll to "Not directly comparable" | "Salt form isn't stated by the source, so we refuse to compare. That honesty costs us features" |
| 1:15 | Search `Telmisartan and Chlorthalidone` | "Real NPPA retail prices from real companies, compared only when identical, and it states exactly what's compared" |
| 1:35 | Add prescription, type `DemoMetacin`, `500 mg` | "Typing is equal to uploading. This name looks like another medicine, so confirm stays locked until you check" |
| 2:00 | Open the item's prices URL before confirming | "Even a direct request gets refused by the server" |
| 2:15 | Confirm, then show the summary | "Confirmed items only, addressed to your doctor or pharmacist. The link expires" |
| 2:35 | Type `I took too many tablets` in search | "Emergency language interrupts everything with 112, in three languages" |
| 2:50 | Switch to Tamil | "Full interface in Hindi and Tamil, pending native-speaker review" |

Videos are in `portfolio/demo/videos/`.
""")
    (OUT / "JUDGE_AND_INTERVIEW_QA.md").write_text(f"""# Judge and interview Q&A

**How accurate is the OCR?**
On synthetic handwriting, character error is {s['cer']}% for {m['selected_engine']} and {o['cer']}% for {m['other_engine']}. I have no real handwriting results, and I expect them to be worse. That's why OCR only proposes.

**Why did you choose the engine with worse text accuracy?**
I fixed the rule before scoring: lowest validation false-match rate. {m['selected_engine']} won narrowly and is faster. Honestly, the false-match difference is within noise, and {m['other_engine']} reads better, so better data should revisit this.

**What is your false-match rate?**
{s['fmr']}% on the test split: {s['false_matches']} of {s['suggested']} suggestions, with a 95% upper bound of {s['fmr_upper']}%. With so few suggestions I can't rule out rare errors, and synthetic data flatters it.

**Why is coverage so low?**
At safe thresholds, only {s['coverage']}% of readable lines get a suggestion. I chose fewer false matches over convenience. A person checks every item anyway.

**Can a user bypass verification?**
Not through the app or API for a prescription item. The server checks the status, a database constraint backs it up, and tests call the API directly. Anyone can still open a public catalogue record they choose, because that says nothing about their prescription.

**Can a user confirm the wrong medicine?**
Yes, and that's the main remaining risk. I added friction, but I haven't measured whether it works with real users.

**Is this real data?**
Partly. {m['catalogue_real']} rows are real NPPA legal maximums: {m['catalogue_ceiling']} ceiling prices and {m['catalogue_retail']} notified retail prices naming real companies. Demo brands and shop prices, Jan Aushadhi entries and regulatory notices are fictional and labelled.

**So does it save anyone money?**
There's no evidence yet. It has no users and no real shop prices, and NPPA's prices vary little between companies.

**Why not use the Jan Aushadhi data, or scrape pharmacy sites?**
The Jan Aushadhi portal's terms ask for permission first, so I need to request it. Scraping against terms isn't acceptable, and retail prices without provenance would break the product's promise.

**Why not use an LLM for everything?**
A model that picks a medicine is hard to explain, test or trust here. Matching and gating are deterministic. An optional adapter exists but is off, isn't connected to the pipeline, and has only been tested with a fake client.

**How do you handle prompt injection?**
The pipeline has no instruction channel, so injected text can only ever appear as text. The detector recognised only about half of injected lines after OCR garbled them, so I don't rely on it.

**Is this a medical device?**
I don't know, and it needs legal review. CDSCO has guidance on medical device software, which I haven't assessed against the final text. See `docs/COMPLIANCE_NOTES.md`.

**How is privacy handled?**
Metadata stripped, private storage, 7-day deletion by default, export and account deletion. Known gaps: one database role, encryption at rest left to the host, and no penetration test.

**What would you do differently?**
Seek data access before building comparison features, and involve a pharmacist much earlier.

**Did you use AI to build this?**
Yes, substantially: Claude Code wrote much of the code and documents under my direction. *(Adjust this to be accurate for you.)*

**What are you proudest of?**
Features I left out because the data couldn't support them, and tests that caught real mistakes.
""")
    (OUT / "LINKEDIN_POST.md").write_text(f"""# LinkedIn post

The same medicine can cost very different amounts depending on the brand in India. But a wrong "cheaper equivalent" could really hurt someone.

So I built a prototype, MediCompare, around one rule: software proposes, a person decides.

- It reads a prescription, but the server shows no prices until a person confirms each medicine
- It compares only products proven identical on ingredient, salt, strength, form, route and release type
- Every price shows its type, source and date
- English, Hindi and Tamil

What I measured: {m['safety_tests']} safety tests, {m['backend_tests']} backend tests at {m['backend_coverage']}% coverage, and an OCR evaluation on {m['images']} synthetic prescriptions, where about one in five unfiltered top matches was wrong. That result is why a person has to confirm.

What it isn't yet: it isn't live, it has no users, and it has no real shop prices. Real data is NPPA's legal price limits, not shop prices. Synthetic handwriting is easier than the real thing.

Built with substantial help from Claude Code. Feedback from pharmacists and doctors is very welcome.
""")


def build_report(m: dict) -> None:
    s = m["engines"][m["selected_engine"]]
    o = m["engines"][m["other_engine"]]
    styles = getSampleStyleSheet()
    body = ParagraphStyle("B", parent=styles["BodyText"], fontSize=10.5, leading=15, spaceAfter=7)
    h1 = ParagraphStyle("H1", parent=styles["Heading1"], fontSize=15, spaceBefore=12, spaceAfter=7, textColor=colors.HexColor("#312e81"), keepWithNext=1)
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=12, spaceBefore=8, spaceAfter=5, keepWithNext=1)
    title = ParagraphStyle("T", parent=styles["Title"], fontSize=26, leading=32, alignment=TA_CENTER)
    centre = ParagraphStyle("C", parent=body, alignment=TA_CENTER)
    small = ParagraphStyle("S", parent=body, fontSize=8.5, leading=11, spaceAfter=0)
    cap = ParagraphStyle("Cap", parent=body, fontSize=9, textColor=colors.HexColor("#52514e"), alignment=TA_CENTER)
    story: list = []

    def p(text: str) -> None:
        story.append(Paragraph(text, body))

    def head(text: str) -> None:
        story.append(CondPageBreak(45 * mm))
        story.append(Paragraph(text, h1))

    def sub(text: str) -> None:
        story.append(Paragraph(text, h2))

    def bullets(items: list[str]) -> None:
        story.append(ListFlowable([ListItem(Paragraph(i, body)) for i in items], bulletType="bullet", start="circle", leftIndent=14))
        story.append(Spacer(1, 4))

    def table(rows: list[list[str]], widths: list[float]) -> None:
        data = [[Paragraph(f"<b>{c}</b>" if r == 0 else str(c), small) for c in row] for r, row in enumerate(rows)]
        t = Table(data, colWidths=[w * mm for w in widths], repeatRows=1)
        t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#9a9a94")), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef0fb")), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        story.extend([t, Spacer(1, 9)])

    def figure(path: Path, caption: str, width: float = 150) -> None:
        from PIL import Image as Pil

        with Pil.open(path) as image:
            ratio = image.height / image.width
        story.extend([Image(str(path), width=width * mm, height=width * mm * ratio), Paragraph(caption, cap)])

    story += [Spacer(1, 70), Paragraph("MediCompare", title), Spacer(1, 10)]
    story.append(Paragraph("A neutral, source-traceable medicine price information system for India, with human-verified prescription reading", centre))
    story += [Spacer(1, 30), Paragraph("Project report", centre), Paragraph("November 2026", centre), Spacer(1, 30)]
    story.append(Paragraph("<b>Information only, not medical advice.</b> This is a prototype. It is not deployed, has not been tested with users, and no regulatory compliance is claimed. Real prices are NPPA legal maximums. Shop prices in this build are fictional demo data.", centre))
    story.append(PageBreak())

    head("Abstract")
    p(f"Medicine prices in India vary widely across brands, yet choosing a cheaper product wrongly can cause harm. This project designs and builds MediCompare, a prototype that treats this risk as the central requirement. Optical character recognition (OCR) only proposes candidates: a person must confirm each medicine, and the server refuses price comparison until they do. Products are compared only when a deterministic rule proves them identical on ingredient, salt form, strength, dosage form, route and release type. {m['catalogue_real']} official NPPA price rows were imported with row-level provenance. Two OCR engines were evaluated on {m['images']} synthetic prescriptions. At thresholds calibrated on validation data, the selected engine made {s['false_matches']} false match(es) in {s['suggested']} suggestions on the test split (95% upper bound {s['fmr_upper']}%), at {s['coverage']}% coverage. The system passes {m['gates_passed']} of {m['gates_total']} automated gates, including {m['safety_tests']} safety tests. The main limitations are that results come from synthetic handwriting, that no real shop prices were available, and that no user testing has taken place.")

    head("1. Introduction")
    p("The same molecule can be sold at very different prices under different brands. Patients and caregivers also struggle to read handwritten prescriptions, distinguish brand from generic names, assess whether a price is trustworthy, and find Jan Aushadhi options. Tools that automate these tasks carry a specific danger: a confident, wrong identification may lead someone to the wrong medicine.")
    p("<b>Objectives:</b> to build a working application that searches medicines, shows only sourced prices, surfaces lower-cost options with their differences, supports Jan Aushadhi discovery, and reads prescriptions with mandatory human verification, and to measure how it behaves rather than assert it.")
    p("<b>Scope:</b> MediCompare is not a pharmacy, prescriber, diagnostic tool, dosing or interaction advisor, or emergency service.")

    head("2. Related work")
    p("Observations were made from public pages and search results in November 2026. They are brief, and are not a full feature audit. Online pharmacies such as Tata 1mg, PharmEasy and Apollo 24|7 sell medicines and accept prescription uploads to fulfil orders, so they are not neutral. Two government tools are closest in spirit: NPPA's Pharma Sahi Daam offers official price lookup, and Janaushadhi Sugam offers a Kendra locator and generic versus branded comparison. MediCompare does not have better data than these. Its contribution is a design pattern: enforced human verification, and refusal to compare what cannot be proven comparable.")

    head("3. Requirements and safety rules")
    bullets([
        "Never guess an unreadable medicine, and never infer dose, frequency, duration, strength or route.",
        "Never let an unverified identity reach comparison, enforced on the server.",
        "Never treat similar names as equivalent.",
        "Present alternatives only as options to discuss with a doctor or pharmacist.",
        "Interrupt on emergency language with India's 112 number.",
        "Never present a ceiling price as a retail price, and never imply stock.",
        "Label all synthetic data, and never fabricate results.",
    ])

    head("4. System design")
    figure(ROOT / "docs/diagrams/c4_container.png", "Figure 1. Container view.", 120)
    sub("4.1 Equivalence")
    p("One pure function compares two products attribute by attribute and returns every difference. Names are not an input, so look-alike names cannot produce a match. Strengths are converted to canonical units, so 250 mg/5 mL equals 50 mg/mL. An unstated salt form cannot prove a match. This has a real cost: NPPA's ceiling lists do not state salts, so those rows rarely compare per unit with other products.")
    sub("4.2 Prescription pipeline")
    p("Uploads are validated by magic bytes and limits, and re-encoded from pixels to remove metadata. Images are deskewed and enhanced with OpenCV. An OCR engine produces text with boxes and quality. Deterministic extraction drops instruction-like text and personal details, then records each field as visible, unclear or unknown. Matching returns explained candidates, and never selects one.")
    figure(ROOT / "docs/diagrams/seq_comparison.png", "Figure 2. Comparison through the verification gate.", 135)
    sub("4.3 The gate")
    p("Price and option routes for a prescription item require status verified, a confirmed medicine and a verifier type. A database constraint rejects a verified row without these. The gate takes no confidence score, so a score can change a label but never access.")
    sub("4.4 Data")
    p(f"NPPA's copyright policy permits reproduction with accuracy and acknowledgement, so its therapeutic-category lists and text-based Authority minutes were parsed from PDF. Scanned minutes were deliberately not read by OCR, since a misread digit would appear as an official price. Imports pass through staging and validation: {m['catalogue_real']} rows were published and {m['review_queue']} wait in a review queue with stated reasons. The Jan Aushadhi portal requires permission to reproduce its data, so that data was not bundled, and demo data stands in. Demo brands all start with \"Demo\", and a data-quality check enforces this.")
    sub("4.5 Privacy and security")
    p("Controls include Argon2id, httpOnly cookies, CSRF tokens, rate limits, lockout, a nonce-based Content Security Policy, private object storage, 7-day retention, data export and hard deletion. A STRIDE threat model is in docs/THREAT_MODEL.md. Known gaps include a single database role, encryption at rest left to the host, and no penetration test.")

    head("5. Evaluation")
    sub("5.1 Method")
    p(f"A seeded generator rendered {m['images']} prescriptions (360 train, 120 validation, 120 test) using eight open-licence handwriting fonts, with rotation, perspective, shadow, blur, noise and low resolution. Hard cases included look-alike brands, missing strengths, fixed-dose combinations, modified release, illegible scribbles and injected instructions. Scoring was strict: any suggestion on a line with a missing strength, an illegible span or non-medicine text counts as a false match. Thresholds and engine choice used validation data only.")
    sub("5.2 Results")
    table([
        ["Test split", f"{m['selected_engine']} (selected)", m["other_engine"]],
        ["Character error rate", f"{s['cer']}%", f"{o['cer']}%"],
        ["Word error rate", f"{s['wer']}%", f"{o['wer']}%"],
        ["Medicine name F1", f"{s['f1']}%", f"{o['f1']}%"],
        ["Top candidate correct", f"{s['top1']}%", f"{o['top1']}%"],
        ["False-match rate, no thresholds", f"{s['unfiltered_fmr']}%", f"{o['unfiltered_fmr']}%"],
        ["False-match rate, calibrated", f"{s['fmr']}% ({s['false_matches']}/{s['suggested']})", f"{o['fmr']}% ({o['false_matches']}/{o['suggested']})"],
        ["95% upper bound", f"{s['fmr_upper']}%", f"{o['fmr_upper']}%"],
        ["Coverage of readable lines", f"{s['coverage']}%", f"{o['coverage']}%"],
        ["Abstention rate", f"{s['abstention']}%", f"{o['abstention']}%"],
        ["Latency per page, p50", f"{s['p50_s']} s", f"{o['p50_s']} s"],
    ], [70, 50, 50])
    figure(ROOT / "docs/diagrams/chart_engines.png", "Figure 3. Engine comparison on the test split.", 130)
    figure(ROOT / "docs/diagrams/chart_tradeoff.png", "Figure 4. Threshold trade-off for the selected engine.", 130)
    figure(ROOT / "docs/diagrams/chart_reliability.png", "Figure 5. Reliability of the match score.", 100)
    sub("5.3 Discussion")
    p(f"Without thresholds, about one top candidate in five was wrong, even on this easy data. This supports the decision that software must not select a medicine. Calibration reduced false matches sharply, at the cost of coverage: most lines receive no suggestion. {m['selected_engine']} was selected by the rule fixed before scoring, but its false-match rate cannot be statistically distinguished from {m['other_engine']}'s, which reads text better. The match score is not a probability, and should not be presented as one.")
    p("<b>Threats to validity.</b> Fonts are far more regular than handwriting, the templates are clean, and only catalogue names appear. With under 100 suggestions per engine, rare serious errors cannot be excluded. Nothing here measures whether people confirm correctly when shown a suggestion. <b>These results do not show real-world accuracy.</b>")

    head("6. Testing and verification")
    table([
        ["Gate", "Result"],
        ["Backend tests", f"{m['backend_tests']} passed; {m['backend_coverage']}% line coverage; {m['core_coverage']}% on core modules"],
        ["Safety invariant suite", f"{m['safety_tests']} passed, including direct API bypass attempts"],
        ["Frontend tests", f"{m['frontend_tests']} passed; {m['frontend_coverage']}% line coverage"],
        ["End-to-end, with axe", f"{m['e2e_tests']} runs across desktop and mobile viewports; no serious or critical violations"],
        ["Load test (local, one laptop)", f"Search p50 {m['search_p50']} ms, p95 {m['search_p95']} ms, p99 {m['search_p99']} ms; {m['perf_requests']} requests, {m['perf_failures']} failures, {m['perf_rps']} requests/s"],
        ["All gates", f"{m['gates_passed']} of {m['gates_total']} passed. See VERIFICATION_REPORT.md"],
    ], [55, 115])
    p("Testing found real defects, including partial words classed as exact search matches, demo accounts unable to sign in, rate limits that would have grouped all users as one address, and virtual environments being copied into container images. One accepted security finding remains: an old PCRE2 library bundled in two Python packages, documented with its rationale. The load test ran with raised rate limits, client and server sharing one machine, so it does not indicate production capacity.")

    head("7. Limitations")
    bullets([
        "No real shop prices exist in this build. Real prices are NPPA legal maximums, which vary little between companies.",
        "Real data covers five ceiling-price categories, dated March 2026 and without salt forms, and new drugs from four sets of minutes.",
        "OCR results are from synthetic data only. No real prescriptions were used.",
        "The look-alike check is a string-similarity screen, not a clinical list.",
        "Hindi and Tamil text is AI-written and awaits native-speaker review.",
        "No user research, pharmacist testing, screen-reader user testing, or low-end device testing has been done.",
        "No legal review has been done. Whether this is medical device software is an open question.",
        "The system is not deployed.",
    ])

    head("8. Conclusion and future work")
    p("MediCompare shows that a medicine price tool can be designed so that safety rules are enforced by the system, and that those rules can be tested. The evaluation supports mandatory human verification, even on favourable data. It does not show that the product helps anyone yet, because that needs real data and real users.")
    bullets([
        "Obtain real shop prices and PMBI permission.",
        "Obtain legal review, beginning with medical device classification.",
        "Run a consented, ethics-approved evaluation on real prescriptions (protocol in docs/EVALUATION.md).",
        "Test with pharmacists and patients, measuring whether people catch wrong suggestions.",
        "Review translations with native speakers, and replace the similarity screen with a clinical list.",
    ])

    head("References")
    for ref in [
        "National Pharmaceutical Pricing Authority. Therapeutic category wise ceiling price list. https://nppa.gov.in/en/therapeuticcategorywiseceilingpricelist (accessed 5 Nov 2026).",
        "National Pharmaceutical Pricing Authority. Copyright policy. https://nppa.gov.in/en/copyrightpolicy (accessed 5 Nov 2026).",
        "Pharmaceuticals and Medical Devices Bureau of India. Janaushadhi portal. https://janaushadhi.gov.in (accessed 5 Nov 2026).",
        "Press Information Bureau. Janaushadhi Sugam launch. https://pib.gov.in/PressReleasePage.aspx?PRID=1583141 (accessed 5 Nov 2026).",
        "Central Drugs Standard Control Organisation. Alerts. https://cdsco.gov.in/opencms/opencms/en/Notifications/Alerts/ (accessed 5 Nov 2026).",
        "Smith, R. An overview of the Tesseract OCR engine. ICDAR, 2007.",
        "RapidOCR project. https://github.com/RapidAI/RapidOCR (accessed 5 Nov 2026).",
    ]:
        story.append(Paragraph(ref, small))
        story.append(Spacer(1, 4))

    def footer(canvas, document):
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#52514e"))
        canvas.drawCentredString(A4[0] / 2, 10 * mm, f"MediCompare project report. Information only, not medical advice. Page {document.page}")

    SimpleDocTemplate(
        str(OUT / "report.pdf"), pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm,
        bottomMargin=18 * mm, title="MediCompare project report", author="MediCompare",
    ).build(story, onFirstPage=footer, onLaterPages=footer)


if __name__ == "__main__":
    measured = metrics()
    (ROOT / "verification/metrics.json").write_text(json.dumps(measured, indent=1))
    write_markdown(measured)
    build_report(measured)
    print("portfolio generated:", {k: measured[k] for k in ("backend_tests", "safety_tests", "e2e_tests", "search_p95")})
