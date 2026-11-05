#!/usr/bin/env python3
"""Fail unless safety, matching and price-comparison modules have at least 95% line coverage."""
import json
import sys

CORE = ("app/safety/", "app/matching/", "app/pricing/", "app/prescriptions/extraction.py", "app/prescriptions/confidence.py")
data = json.load(open(sys.argv[1]))
covered = total = 0
for path, entry in data["files"].items():
    if path.startswith(CORE):
        summary = entry["summary"]
        covered += summary["covered_lines"]
        total += summary["num_statements"]
        print(f"{path}: {summary['percent_covered']:.1f}%")
percent = 100 * covered / total
print(f"core modules: {percent:.1f}% ({covered}/{total})")
sys.exit(0 if percent >= 95 else 1)
