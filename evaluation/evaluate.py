"""Score stored OCR output against ground truth, calibrate on validation, report on test.

Run after run_ocr.py: python evaluation/evaluate.py
Writes evaluation/results/results.json, charts, and backend/app/prescriptions/thresholds.json.

Scoring is deliberately strict:
- A generic line is correct only if the top candidate has the same ingredients, strengths, form and
  release type. A brand line is correct only if the top candidate is that exact product.
- A suggestion on a line with missing strength, on an illegible span, or on text that is not a
  medicine line counts as a false match. In those cases the safe behaviour is to abstain.
"""

from __future__ import annotations

import csv
import json
import math
import statistics
import sys
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from rapidfuzz import fuzz  # noqa: E402
from rapidfuzz.distance import Levenshtein  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "evaluation"))

from generate import composition_key, load_catalogue  # noqa: E402

from app.matching.equivalence import Strength  # noqa: E402
from app.matching.matcher import CatalogueEntry, match  # noqa: E402
from app.prescriptions.extraction import extract  # noqa: E402
from app.prescriptions.ocr import TextSpan, spans_to_lines  # noqa: E402

RESULTS = ROOT / "evaluation/results"
DATASET = ROOT / "evaluation/datasets/v1"
ENGINES = ["tesseract", "rapidocr"]
OCR_GRID = [0.0, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95]
MATCH_GRID = [0.62, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.92, 0.95, 0.97, 1.0]
MIN_VALIDATION_SUGGESTIONS = 20
SERIES = {"tesseract": "#2a78d6", "rapidocr": "#eb6834"}
SURFACE, INK, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e0"


@dataclass
class Scored:
    """One extracted item with its top candidate, marked correct or not."""

    ocr_quality: float
    match_quality: float | None
    correct: bool
    tags: tuple[str, ...]
    aligned: bool


def catalogue_entries() -> tuple[list[CatalogueEntry], dict[int, str], dict[int, str]]:
    entries, compositions, names = [], {}, {}
    for index, row in enumerate(load_catalogue()):
        strengths = tuple(
            sorted(
                Strength(
                    Decimal(i["strength_value"]), i["strength_unit"],
                    Decimal(i["per_value"]) if i["per_value"] else None, i["per_unit"],
                ).canonical()
                for i in row["ingredients"]
            )
        )
        entries.append(
            CatalogueEntry(
                index, row["display_name"], row["brand"], tuple(i["name"] for i in row["ingredients"]),
                strengths, row["dosage_form"], row["release_type"],
            )
        )
        compositions[index] = composition_key(row)
        names[index] = row["display_name"]
    return entries, compositions, names


def normal(text: str) -> str:
    return " ".join(text.lower().split())


def truth_text(truth: dict) -> str:
    parts = [*truth["header"], "Rx"]
    parts += [line["text"] for line in truth["lines"] if line.get("text")]
    return normal(" ".join(parts))


def score_image(truth: dict, raw: dict, entries, compositions, names) -> dict:
    spans = [TextSpan(s["text"], tuple(s["bbox"]), s["quality"]) for s in raw["spans"]]
    lines = spans_to_lines(spans)
    ocr_text = normal(" ".join(line.text for line in lines))
    reference = truth_text(truth)
    char_distance = Levenshtein.distance(ocr_text, reference)
    word_distance = Levenshtein.distance(ocr_text.split(), reference.split())
    result = extract(lines)
    medicine_truth = [
        line for line in truth["lines"]
        if not line.get("instruction") and not line.get("illegible")
    ]
    remaining = list(medicine_truth)
    scored: list[Scored] = []
    name_tp = 0
    for item in result.items:
        best, best_score = None, 0.0
        for line in remaining:
            value = fuzz.ratio(normal(item.source_text), normal(line["text"]))
            if value > best_score:
                best, best_score = line, value
        aligned = best is not None and best_score >= 55
        if aligned:
            remaining.remove(best)
            if item.name.value and fuzz.ratio(normal(item.name.value), normal(best["name"])) >= 90:
                name_tp += 1
        candidates = match(item.name.value, item.strength.value, item.form.value, entries)
        top = candidates[0] if candidates else None
        correct = False
        if top is not None and aligned and "missing_strength" not in best["tags"]:
            if best["written_as"] == "brand":
                correct = names[top.medicine_id] == best["display_name"]
            else:
                correct = compositions[top.medicine_id] == best["composition"]
        tags = tuple(best["tags"]) if aligned else ("not_a_medicine_line",)
        scored.append(Scored(item.quality, top.score if top else None, correct, tags, aligned))
    return {
        "char_distance": char_distance,
        "chars": len(reference),
        "word_distance": word_distance,
        "words": len(reference.split()),
        "name_tp": name_tp,
        "predicted": len(result.items),
        "truth_lines": len(medicine_truth),
        "identifiable_lines": sum("missing_strength" not in line["tags"] for line in medicine_truth),
        "scored": scored,
        "instruction_lines_dropped": result.instruction_lines,
        "injection_present": sum(bool(line.get("instruction")) for line in truth["lines"]),
        "redacted": result.redacted_lines,
        "degradations": truth["degradations"],
        "latency_ms": raw["preprocess_ms"] + raw["ocr_ms"],
    }


def at_threshold(images: list[dict], min_ocr: float, min_match: float) -> dict:
    suggested = wrong = correct = 0
    for image in images:
        for item in image["scored"]:
            if item.match_quality is None or item.match_quality < min_match or item.ocr_quality < min_ocr:
                continue
            suggested += 1
            correct += item.correct
            wrong += not item.correct
    truth = sum(image["truth_lines"] for image in images)
    identifiable = sum(image["identifiable_lines"] for image in images)
    return {
        "min_ocr_quality": min_ocr,
        "min_match_quality": min_match,
        "suggested": suggested,
        "correct_suggestions": correct,
        "false_matches": wrong,
        "false_match_rate": wrong / suggested if suggested else None,
        "false_match_rate_upper_95": wilson_upper(wrong, suggested),
        "coverage_of_identifiable_lines": correct / identifiable if identifiable else None,
        "abstention_rate": 1 - min(suggested, truth) / truth if truth else None,
    }


def wilson_upper(failures: int, total: int, z: float = 1.96) -> float | None:
    if total == 0:
        return None
    rate = failures / total
    centre = rate + z * z / (2 * total)
    margin = z * math.sqrt(rate * (1 - rate) / total + z * z / (4 * total * total))
    return (centre + margin) / (1 + z * z / total)


def summary(images: list[dict]) -> dict:
    predicted = sum(i["predicted"] for i in images)
    truth = sum(i["truth_lines"] for i in images)
    name_tp = sum(i["name_tp"] for i in images)
    precision = name_tp / predicted if predicted else 0.0
    recall = name_tp / truth if truth else 0.0
    identifiable = sum(i["identifiable_lines"] for i in images)
    correct_top1 = sum(item.correct for i in images for item in i["scored"])
    latencies = sorted(i["latency_ms"] for i in images)
    return {
        "images": len(images),
        "truth_medicine_lines": truth,
        "cer": sum(i["char_distance"] for i in images) / max(sum(i["chars"] for i in images), 1),
        "wer": sum(i["word_distance"] for i in images) / max(sum(i["words"] for i in images), 1),
        "entity_precision": precision,
        "entity_recall": recall,
        "entity_f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
        "exact_match_accuracy_top1": correct_top1 / identifiable if identifiable else 0.0,
        "uncalibrated": at_threshold(images, 0.0, 0.0),
        "latency_ms_mean": statistics.mean(latencies),
        "latency_ms_p50": latencies[len(latencies) // 2],
        "latency_ms_p95": latencies[int(len(latencies) * 0.95) - 1],
        "injection_lines_present": sum(i["injection_present"] for i in images),
        "injection_lines_dropped": sum(i["instruction_lines_dropped"] for i in images),
    }


def calibrate(images: list[dict]) -> dict:
    """Lowest false-match rate on validation, then highest coverage. Test data is not used."""
    grid = [at_threshold(images, o, m) for o in OCR_GRID for m in MATCH_GRID]
    usable = [g for g in grid if g["suggested"] >= MIN_VALIDATION_SUGGESTIONS]
    if not usable:
        return {"min_ocr_quality": 1.0, "min_match_quality": 1.0, "note": "no usable threshold", "grid_size": len(grid)}
    best = min(
        usable,
        key=lambda g: (g["false_match_rate"], -g["correct_suggestions"], -g["min_ocr_quality"], -g["min_match_quality"]),
    )
    return {**best, "grid_size": len(grid)}


def by_tag(images: list[dict], min_ocr: float, min_match: float) -> dict:
    groups: dict[str, list[Scored]] = defaultdict(list)
    for image in images:
        for item in image["scored"]:
            for tag in item.tags or ("plain",):
                groups[tag].append(item)
    table = {}
    for tag, items in sorted(groups.items()):
        passed = [
            i for i in items
            if i.match_quality is not None and i.match_quality >= min_match and i.ocr_quality >= min_ocr
        ]
        table[tag] = {
            "items": len(items),
            "suggested": len(passed),
            "correct": sum(i.correct for i in passed),
            "false_matches": sum(not i.correct for i in passed),
        }
    return table


def by_degradation(images: list[dict], min_ocr: float, min_match: float) -> dict:
    table = {}
    for name in ["rotation", "perspective", "shadow", "blur", "noise", "low_resolution"]:
        subset = [i for i in images if name in i["degradations"]]
        if subset:
            row = at_threshold(subset, min_ocr, min_match)
            table[name] = {
                "images": len(subset),
                "cer": sum(i["char_distance"] for i in subset) / max(sum(i["chars"] for i in subset), 1),
                "suggested": row["suggested"],
                "false_matches": row["false_matches"],
                "coverage": row["coverage_of_identifiable_lines"],
            }
    return table


def reliability(images: list[dict], edges: list[float]) -> list[dict]:
    bins = []
    for low, high in zip(edges, edges[1:], strict=False):
        items = [
            item for image in images for item in image["scored"]
            if item.match_quality is not None and low <= item.match_quality < high
        ]
        if items:
            bins.append(
                {
                    "low": low,
                    "high": high,
                    "count": len(items),
                    "mean_score": statistics.mean(i.match_quality for i in items),
                    "observed_correct": sum(i.correct for i in items) / len(items),
                }
            )
    return bins


def style(axis) -> None:
    axis.set_facecolor(SURFACE)
    for side in ("top", "right"):
        axis.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        axis.spines[side].set_color(GRID)
    axis.tick_params(colors=MUTED, length=0)
    axis.grid(axis="y", color=GRID, linewidth=0.8)
    axis.set_axisbelow(True)


def figure(width: float = 8, height: float = 4.4):
    fig, axis = plt.subplots(figsize=(width, height), dpi=160, facecolor=SURFACE)
    style(axis)
    return fig, axis


def chart_engines(results: dict) -> None:
    metrics = [
        ("cer", "Character error"),
        ("wer", "Word error"),
        ("entity_f1", "Name F1"),
        ("exact_match_accuracy_top1", "Top-1 identity"),
    ]
    fig, axis = figure()
    width = 0.34
    for offset, engine in zip((-0.18, 0.18), ENGINES, strict=True):
        values = [results["engines"][engine]["test"][key] * 100 for key, _ in metrics]
        positions = [index + offset for index in range(len(metrics))]
        bars = axis.bar(positions, values, width, color=SERIES[engine], label=engine, edgecolor=SURFACE, linewidth=1.5)
        for bar, value in zip(bars, values, strict=True):
            axis.text(bar.get_x() + bar.get_width() / 2, value + 1.2, f"{value:.1f}", ha="center", color=INK, fontsize=8)
    axis.set_xticks(range(len(metrics)), [label for _, label in metrics], color=INK)
    axis.set_ylabel("Percent (test split)", color=MUTED)
    axis.set_ylim(0, 110)
    axis.set_title("Lower error is better; higher F1 and identity are better", color=INK, loc="left", fontsize=11)
    axis.legend(frameon=False, loc="upper left", ncols=2, bbox_to_anchor=(0, 0.99))
    fig.tight_layout()
    fig.savefig(RESULTS / "chart_engines.png")
    plt.close(fig)


def chart_tradeoff(results: dict) -> None:
    chosen = results["selected_engine"]
    rows = results["engines"][chosen]["tradeoff_test"]
    xs = [row["min_match_quality"] for row in rows]
    false_rate = [(row["false_match_rate"] or 0) * 100 for row in rows]
    coverage = [(row["coverage_of_identifiable_lines"] or 0) * 100 for row in rows]
    fig, axis = figure()
    axis.plot(xs, coverage, color=SERIES["tesseract"], linewidth=2, marker="o", markersize=5, label="Coverage of readable lines")
    axis.plot(xs, false_rate, color=SERIES["rapidocr"], linewidth=2, marker="s", markersize=5, label="False-match rate")
    threshold = results["engines"][chosen]["calibration"]["min_match_quality"]
    axis.axvline(threshold, color=MUTED, linewidth=1, linestyle="--")
    axis.text(threshold - 0.005, 103, "chosen on validation", color=MUTED, fontsize=8, ha="right")
    axis.set_xlabel("Minimum match score", color=MUTED)
    axis.set_ylabel("Percent (test split)", color=MUTED)
    axis.set_ylim(0, 108)
    axis.set_title(f"{chosen}: stricter thresholds trade coverage for fewer false matches", color=INK, loc="left", fontsize=11)
    axis.legend(frameon=False, loc="center left")
    fig.tight_layout()
    fig.savefig(RESULTS / "chart_tradeoff.png")
    plt.close(fig)


def chart_reliability(results: dict) -> None:
    fig, axis = figure(6, 4.8)
    axis.plot([0.6, 1], [0.6, 1], color=MUTED, linewidth=1, linestyle="--", label="Perfect calibration")
    for engine in ENGINES:
        bins = results["engines"][engine]["reliability_test"]
        axis.plot(
            [b["mean_score"] for b in bins], [b["observed_correct"] for b in bins], color=SERIES[engine], linewidth=2,
            marker="o" if engine == "tesseract" else "s", markersize=6, label=engine,
        )
    axis.set_xlabel("Match score (bin mean)", color=MUTED)
    axis.set_ylabel("Share of top candidates that were correct", color=MUTED)
    axis.set_xlim(0.6, 1.02)
    axis.set_ylim(0, 1.05)
    axis.set_title("Reliability of the match score (test split)", color=INK, loc="left", fontsize=11)
    axis.legend(frameon=False, loc="lower right")
    fig.tight_layout()
    fig.savefig(RESULTS / "chart_reliability.png")
    plt.close(fig)


def main() -> None:
    entries, compositions, names = catalogue_entries()
    truth_by_id = {}
    for split in ("train", "validation", "test"):
        for path in (DATASET / split).glob("*.json"):
            truth_by_id[path.stem] = json.loads(path.read_text())
    results: dict = {"seed_manifest": json.loads((DATASET / "manifest.json").read_text())["seed"], "engines": {}}
    for engine in ENGINES:
        raw_rows = [json.loads(line) for line in open(RESULTS / f"raw_{engine}.jsonl", encoding="utf-8")]
        meta = json.loads((RESULTS / f"raw_{engine}.meta.json").read_text())
        grouped: dict[str, list[dict]] = defaultdict(list)
        for raw in raw_rows:
            truth = truth_by_id[raw["id"]]
            grouped[truth["split"]].append(score_image(truth, raw, entries, compositions, names))
        calibration = calibrate(grouped["validation"])
        min_ocr, min_match = calibration["min_ocr_quality"], calibration["min_match_quality"]
        results["engines"][engine] = {
            "meta": meta,
            "train": summary(grouped["train"]),
            "validation": summary(grouped["validation"]),
            "test": summary(grouped["test"]),
            "calibration": calibration,
            "calibrated_test": at_threshold(grouped["test"], min_ocr, min_match),
            "tradeoff_test": [at_threshold(grouped["test"], min_ocr, m) for m in MATCH_GRID],
            "by_tag_test": by_tag(grouped["test"], min_ocr, min_match),
            "by_degradation_test": by_degradation(grouped["test"], min_ocr, min_match),
            "reliability_test": reliability(grouped["test"], [0.6, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1.01]),
        }
    # Engine choice uses validation data only, so the test split stays an unbiased report.
    results["selected_engine"] = min(
        ENGINES,
        key=lambda e: (
            results["engines"][e]["calibration"].get("false_match_rate", 1.0),
            -results["engines"][e]["calibration"].get("correct_suggestions", 0),
        ),
    )
    chosen = results["engines"][results["selected_engine"]]["calibration"]
    thresholds_path = ROOT / "backend/app/prescriptions/thresholds.json"
    thresholds_path.write_text(
        json.dumps(
            {
                "min_ocr_quality": chosen["min_ocr_quality"],
                "min_match_quality": chosen["min_match_quality"],
                "engine": results["selected_engine"],
                "note": "Generated by evaluation/evaluate.py from the validation split of synthetic data.",
            },
            indent=2,
        )
        + "\n"
    )
    (RESULTS / "results.json").write_text(json.dumps(results, indent=1, default=str))
    chart_engines(results)
    chart_tradeoff(results)
    chart_reliability(results)
    with open(RESULTS / "summary.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["engine", "split", "cer", "wer", "f1", "top1", "latency_p50_ms"])
        for engine in ENGINES:
            for split in ("train", "validation", "test"):
                row = results["engines"][engine][split]
                writer.writerow(
                    [engine, split, round(row["cer"], 4), round(row["wer"], 4), round(row["entity_f1"], 4),
                     round(row["exact_match_accuracy_top1"], 4), round(row["latency_ms_p50"])]
                )
    print(json.dumps({e: {"test": {k: v for k, v in results["engines"][e]["test"].items() if k != "uncalibrated"},
                          "calibration": results["engines"][e]["calibration"],
                          "calibrated_test": results["engines"][e]["calibrated_test"]} for e in ENGINES}, indent=1))
    print("selected", results["selected_engine"])


if __name__ == "__main__":
    main()
