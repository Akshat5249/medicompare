"""Shareable summaries. Built only from verified items, so unverified text cannot appear."""

from __future__ import annotations

import io
from datetime import UTC, datetime
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy.orm import Session

from app.catalogue.service import DISCUSS_STATEMENT, get_medicine, lower_cost_options
from app.models import ItemStatus, Prescription
from app.safety.gate import require_verified


def build_summary(
    db: Session, prescription: Prescription, label: str | None = None
) -> dict[str, Any]:
    medicines: list[dict[str, Any]] = []
    for item in prescription.items:
        if item.status != ItemStatus.verified.value:
            continue
        medicine_id = require_verified(item)
        medicine = get_medicine(db, medicine_id)
        if medicine is None:
            continue
        options = lower_cost_options(db, medicine)
        medicines.append(
            {
                "verified_by": item.verified_by_type,
                "verified_at": item.verified_at.isoformat() if item.verified_at else None,
                "medicine": options["reference"]["medicine"],
                "prices": options["reference"]["prices"],
                "options": options["equivalents"],
                "not_equivalent": options["not_equivalent"],
                "jan_aushadhi": options["jan_aushadhi"],
            }
        )
    open_items = sum(item.status != ItemStatus.verified.value for item in prescription.items)
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "label": label,
        "medicines": medicines,
        "items_not_included": open_items,
        "statement": DISCUSS_STATEMENT,
        "notice": "Information only, not medical advice. Unverified items are never included.",
        "contains_demo_data": any(entry["medicine"]["is_demo"] for entry in medicines),
    }


def _esc(value: Any) -> str:
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _price_line(price: dict[str, Any]) -> str:
    stale = " (may be out of date)" if price["is_stale"] else ""
    demo = " [Demo data]" if price["is_demo"] else ""
    return (
        f"{_esc(price['price_type_label'])}: Rs {price['amount_inr']} for {_esc(price['pack'])} "
        f"(Rs {price['per_unit_inr']} per {_esc(price['pack_unit'])}). Source: {_esc(price['source']['name'])}, "
        f"{price['observed_at']}{stale}{demo}"
    )


def render_pdf(summary: dict[str, Any]) -> bytes:
    """English-only PDF: ReportLab cannot shape Indic scripts (see docs/DECISIONS.md)."""
    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title="MediCompare summary",
        author="MediCompare",
    )
    styles = getSampleStyleSheet()
    small = ParagraphStyle("small", parent=styles["BodyText"], fontSize=8.5, leading=11)
    story: list[Any] = [Paragraph("MediCompare summary", styles["Title"])]
    if summary.get("label"):
        story.append(Paragraph(_esc(summary["label"]), styles["Heading3"]))
    story.append(Paragraph(f"<b>{_esc(summary['statement'])}</b>", styles["BodyText"]))
    story.append(Paragraph(_esc(summary["notice"]), small))
    if summary["contains_demo_data"]:
        story.append(
            Paragraph(
                "<b>Demo data: this summary includes fictional medicines and prices.</b>", small
            )
        )
    story.append(Paragraph(f"Generated {_esc(summary['generated_at'][:16])} UTC", small))
    story.append(Spacer(1, 6))
    if not summary["medicines"]:
        story.append(Paragraph("No verified medicines yet.", styles["BodyText"]))
    for entry in summary["medicines"]:
        medicine = entry["medicine"]
        story.append(Paragraph(_esc(medicine["display_name"]), styles["Heading3"]))
        composition = "; ".join(
            f"{i['name']} ({i['salt_form'] or 'salt form not stated'}) {i['strength']}"
            for i in medicine["ingredients"]
        )
        story.append(
            Paragraph(
                f"{_esc(composition)}. {_esc(medicine['dosage_form'])}; {_esc(medicine['release_type'])}; "
                f"{_esc(medicine['route'])}. Verified by: {_esc(entry['verified_by'])}.",
                small,
            )
        )
        for price in entry["prices"]:
            story.append(Paragraph(_price_line(price), small))
        for flag in medicine["regulatory_flags"]:
            story.append(
                Paragraph(
                    f"<b>Regulatory notice:</b> {_esc(flag['description'])} "
                    f"({_esc(flag['source_name'])}, {flag['source_date']})",
                    small,
                )
            )
        rows: list[list[Any]] = [
            [Paragraph("<b>Option to discuss</b>", small), Paragraph("<b>Details</b>", small)]
        ]
        for option in entry["options"]:
            details = [_price_line(price) for price in option["prices"]] or [
                "No sourced price available."
            ]
            details += [_esc(diff["detail"]) for diff in option["differences"]]
            details += [_esc(saving["statement"]) for saving in option["savings"]]
            rows.append(
                [
                    Paragraph(_esc(option["medicine"]["display_name"]), small),
                    Paragraph("<br/>".join(details), small),
                ]
            )
        if len(rows) > 1:
            table = Table(rows, colWidths=[55 * mm, 119 * mm], repeatRows=1)
            table.setStyle(
                TableStyle(
                    [
                        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                    ]
                )
            )
            story += [Spacer(1, 4), table]
        for product in entry["jan_aushadhi"]:
            story.append(
                Paragraph(
                    f"Jan Aushadhi catalogue listing: {_esc(product['generic_name'])}, Rs {product['mrp_inr']} for "
                    f"{_esc(product['unit_size'])} ({_esc(product['source']['name'])}, {product['observed_at']}). "
                    "A listing does not confirm it is available at any Kendra.",
                    small,
                )
            )
        story.append(Spacer(1, 6))
    document.build(story)
    return buffer.getvalue()
