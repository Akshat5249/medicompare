"""Extract retail price tables from NPPA Authority minutes into raw CSV rows.

Only PDFs with a real text layer are read. Scanned minutes are listed and skipped on purpose:
OCR could misread a digit, and a wrong price would then look official.

Usage: python nppa_minutes.py <pdf-dir> <out.csv> <skipped.csv>
"""

from __future__ import annotations

import csv
import logging
import re
import sys
from pathlib import Path

import pdfplumber
import pypdf

logging.getLogger("pdfminer").setLevel(logging.ERROR)
COLUMNS = ["serial", "agenda", "formulation", "composition", "unit", "company", "price"]
FIELDS = ["meeting", "meeting_date", "source_pdf", "page", *COLUMNS, "note"]


def clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").replace("\n", " ")).strip()


def is_scanned(path: Path) -> bool:
    reader = pypdf.PdfReader(str(path))
    return sum(len(page.extract_text() or "") for page in reader.pages) < 200


def read_minutes(path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with pdfplumber.open(path) as pdf:
        pages = [page.extract_text() or "" for page in pdf.pages]
        full = "\n".join(pages)
        date_match = re.search(r"held\s+on\s+(\d{2})\.(\d{2})\.(\d{4})", full)
        if not date_match:
            raise ValueError(f"No meeting date found in {path.name}")
        meeting_date = f"{date_match[3]}-{date_match[2]}-{date_match[1]}"
        meeting = re.search(r"(\d+)", path.stem)[1]  # type: ignore[index]
        notes = {
            number: clean(text)
            for number, text in re.findall(r"Note-(\d+):\s*(.+?)(?=Note-\d+:|\n\d+\.\s+Agenda|\Z)", full, re.S)
        }
        in_table = False
        for number, page in enumerate(pdf.pages, start=1):
            for table in page.extract_tables():
                if not table or len(table[0]) != 7:
                    in_table = False
                    continue
                first = clean(table[0][-1])
                if "Retail" in first:
                    in_table = True
                elif not in_table:
                    continue
                for raw in table:
                    cells = [clean(cell) for cell in raw]
                    if cells[0].isdigit():
                        rows.append(
                            {"meeting": meeting, "meeting_date": meeting_date, "source_pdf": path.name,
                             "page": str(number), **dict(zip(COLUMNS, cells, strict=True)), "note": ""}
                        )
                    elif not cells[0] and rows and any(cells):
                        # A row that continues from the previous page.
                        for column, cell in zip(COLUMNS, cells, strict=True):
                            if cell:
                                rows[-1][column] = clean(f"{rows[-1][column]} {cell}")
    expanded: list[dict[str, str]] = []
    for row in rows:
        note = re.search(r"Note-(\d+)", row["price"])
        if note:
            row["note"] = notes.get(note[1], f"Note-{note[1]}")[:600]
        # "(i) M/s A / M/s B (ii) M/s C / M/s D": one approved price for each named applicant.
        applicants = [part.strip() for part in re.split(r"\((?:i|ii|iii|iv|v)\)\s*(?=M\s*/\s*s)", row["company"]) if part.strip()]
        for applicant in applicants or [row["company"]]:
            expanded.append({**row, "company": applicant})
    return expanded


def main(pdf_dir: str, out_csv: str, skipped_csv: str) -> int:
    rows: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []
    for path in sorted(Path(pdf_dir).glob("minutes-*.pdf")):
        if is_scanned(path):
            skipped.append({"source_pdf": path.name, "reason": "scanned image with no text layer; not read by OCR"})
            continue
        found = read_minutes(path)
        print(f"{path.name}: {len(found)} rows")
        rows += found
    with open(out_csv, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    with open(skipped_csv, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["source_pdf", "reason"])
        writer.writeheader()
        writer.writerows(skipped)
    print(f"TOTAL rows={len(rows)} scanned_skipped={len(skipped)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(*sys.argv[1:4]))
