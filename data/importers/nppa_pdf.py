"""Parse NPPA "therapeutic category wise ceiling price list" PDFs into normalised CSV rows.

Each PDF row is: serial, medicine name, dosage form, strength, unit, ceiling price (INR).
pypdf sometimes splits one row across several lines, so tokens are re-joined between serials.
Rows that cannot be parsed are reported, never guessed.

Usage: python nppa_pdf.py <pdf-dir> <out.csv> <failures.csv>
"""

from __future__ import annotations

import csv
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import pypdf

CATEGORY_BY_SLUG = {
    "anti-cancer": "anti-cancer",
    "anti-diabetes": "anti-diabetes",
    "anti-hiv": "anti-hiv",
    "anti-tb": "anti-tb",
    "cardio": "cardiovascular",
}
FORM_WORDS = (
    r"Powder\s*for\s*(?:I\.?V\.?\s*)?Injection|Solution\s+for\s+Injection|"
    "Oral Liquid|Oral Suspension|Oral Solution|Dry Syrup|Tablet|Capsule|Injection|Syrup|Suspension|"
    "Inhalation|Infusion|Powder|Drops|Solution|Cream|Ointment|Gel|Lozenge|Sachet|Pellets|Granules"
)
ROW = re.compile(
    rf"^(?P<serial>\d{{1,4}})\s+(?P<name>.+?)\s+(?P<form>(?:(?:Modified|Extended|Sustained|Prolonged)"
    rf"\s+Release\s+|Film\s+Coated\s+|Dispersible\s+|ER\s+|SR\s+|MR\s+)?(?:{FORM_WORDS})(?:\s*\([^)]*\))?)"
    r"\s*(?P<strength>\S.*?)\s+(?P<unit>(?:\d+|Each)\s*(?:Tablet|Capsule|ML|mL|Ml|Vial|Pack|Sachet|Dose|gm|g|"
    r"Ampoule|Bottle|Syringe|Each|Unit)s?)\s+(?P<price>\d[\d,]*(?:\.\d+)?)\s*$",
    re.IGNORECASE,
)
SERIAL_START = re.compile(r"^\d{1,4}\s*$|^\d{1,4}\s+\S")


@dataclass
class Row:
    source_pdf: str
    category: str
    serial: int
    name: str
    dosage_form: str
    strength: str
    unit_text: str
    ceiling_price_inr: str
    as_on_text: str


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def parse_pdf(path: Path) -> tuple[list[Row], list[dict[str, str]]]:
    slug = next((s for s in CATEGORY_BY_SLUG if f"-{s}-" in path.name), None)
    if slug is None:
        raise ValueError(f"Unknown NPPA category file: {path.name}")
    reader = pypdf.PdfReader(str(path))
    full = "\n".join(page.extract_text() or "" for page in reader.pages)
    as_on_match = re.search(r"\*?As on ([A-Za-z]+,?\s*\d{4})", full)
    as_on = as_on_match.group(1) if as_on_match else ""
    records: list[str] = []
    current: list[str] = []
    expected = 1
    for raw in full.splitlines():
        line = _clean(raw)
        if not line or re.search(r"[ऀ-ॿ]", line) or "nppa.gov.in" in line.lower():
            continue
        if line.lower().startswith(("*as on", "s.no", "sl.", "as on")):
            continue
        match = re.match(r"^(\d{1,4})(?:\s|$)", line)
        if match and int(match.group(1)) == expected:
            if current:
                records.append(_clean(" ".join(current)))
            current = [line]
            expected += 1
        elif current:
            current.append(line)
    if current:
        records.append(_clean(" ".join(current)))

    rows: list[Row] = []
    failures: list[dict[str, str]] = []
    for record in records:
        # Each page ends with a footer note that pypdf attaches to the page's last row.
        record = _clean(record.split("Please note")[0])
        parsed = ROW.match(record)
        if not parsed:
            failures.append({"source_pdf": path.name, "record": record, "error": "row_shape"})
            continue
        rows.append(
            Row(
                source_pdf=path.name,
                category=CATEGORY_BY_SLUG[slug],
                serial=int(parsed["serial"]),
                name=_clean(parsed["name"]),
                dosage_form=_clean(parsed["form"]),
                strength=_clean(parsed["strength"]),
                unit_text=_clean(parsed["unit"]),
                ceiling_price_inr=parsed["price"].replace(",", ""),
                as_on_text=as_on,
            )
        )
    return rows, failures


def main(pdf_dir: str, out_csv: str, failures_csv: str) -> int:
    all_rows: list[Row] = []
    all_failures: list[dict[str, str]] = []
    for pdf in sorted(Path(pdf_dir).glob("*fb-posts*.pdf")):
        rows, failures = parse_pdf(pdf)
        print(f"{pdf.name}: parsed={len(rows)} failed={len(failures)}")
        all_rows += rows
        all_failures += failures
    with open(out_csv, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(Row.__dataclass_fields__))
        writer.writeheader()
        writer.writerows(asdict(r) for r in all_rows)
    with open(failures_csv, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["source_pdf", "record", "error"])
        writer.writeheader()
        writer.writerows(all_failures)
    print(f"TOTAL parsed={len(all_rows)} failed={len(all_failures)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(*sys.argv[1:4]))
