#!/usr/bin/env python3
"""Validate openapi.yaml, confirm it matches the code, and check internal Markdown links."""
import json
import re
import sys
from pathlib import Path

import yaml
from openapi_spec_validator import validate

ROOT = Path(__file__).resolve().parents[1]
spec = yaml.safe_load((ROOT / "docs/openapi.yaml").read_text())
validate(spec)
print(f"openapi valid: {spec['openapi']}, {len(spec['paths'])} paths")
sys.path.insert(0, str(ROOT / "backend"))
from app.main import app  # noqa: E402

live = json.loads(json.dumps(app.openapi()))
if live != spec:
    print("FAIL docs/openapi.yaml differs from the code; run python scripts/export_openapi.py")
    sys.exit(1)
print("openapi matches code")
bad = 0
checked = 0
files = [p for p in ROOT.rglob("*.md") if not any(x in p.parts for x in ("node_modules", ".venv", ".next", "datasets", "logs"))]
for path in files:
    for target in re.findall(r"\]\(([^)\s]+)\)", path.read_text(encoding="utf-8")):
        if target.startswith(("http://", "https://", "mailto:", "#", "tel:")):
            continue
        checked += 1
        if not (path.parent / target.split("#")[0]).exists():
            print(f"BROKEN {path.relative_to(ROOT)} -> {target}")
            bad += 1
print(f"links checked: {checked}, broken: {bad}")
sys.exit(1 if bad else 0)
