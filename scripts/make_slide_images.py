#!/usr/bin/env python3
"""Crop screenshots to the part each slide needs, and record sizes for build_deck.js."""

import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / "portfolio/demo/screenshots"
OUT = ROOT / "portfolio/demo/slides"
OUT.mkdir(parents=True, exist_ok=True)
CROPS = {
    "search": ("desktop-search-typo.png", 0, 760),
    "price": ("desktop-medicine-real.png", 780, 1270),
    "verify": ("desktop-verify-upload.png", 90, 830),
    "gate": ("desktop-gate-blocked.png", 0, 420),
    "emergency": ("desktop-emergency.png", 0, 800),
}
sizes = {}
for name, (source, top, bottom) in CROPS.items():
    with Image.open(SHOTS / source) as image:
        cropped = image.convert("RGB").crop((0, top, image.width, min(bottom, image.height)))
        cropped.save(OUT / f"{name}.png", optimize=True)
        sizes[name] = {"w": cropped.width, "h": cropped.height}
with Image.open(ROOT / "docs/diagrams/c4_container.png") as image:
    image.convert("RGB").save(OUT / "container.png", optimize=True)
    max_w, max_h = 7.4, 5.1
    scale = min(max_w / image.width, max_h / image.height)
    sizes["containerFit"] = {"w": round(image.width * scale, 3), "h": round(image.height * scale, 3)}
(OUT / "sizes.json").write_text(json.dumps(sizes))
print(sizes)
