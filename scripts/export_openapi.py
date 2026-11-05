#!/usr/bin/env python3
"""Write docs/openapi.yaml from the code."""
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.main import app  # noqa: E402

spec = json.loads(json.dumps(app.openapi()))
(ROOT / "docs/openapi.yaml").write_text(yaml.safe_dump(spec, sort_keys=False, allow_unicode=True))
print("wrote docs/openapi.yaml", spec["openapi"], len(spec["paths"]), "paths")
