#!/usr/bin/env python3
"""Copy Playwright videos of the main flows into portfolio/demo and build the README GIF."""

import json
import shutil
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "frontend/test-results"
DEMO = ROOT / "portfolio/demo"
SHOTS = DEMO / "screenshots"
VIDEOS = DEMO / "videos"
FLOWS = {
    "manual path": "prescription-verify-compare-share",
    "user shares": "pharmacist-review",
    "upload path": "prescription-upload-ocr",
    "emergency input": "emergency-interrupt",
    "look-alike": "look-alike-check",
    "detail shows": "search-and-prices",
    "Jan Aushadhi": "jan-aushadhi",
    "admin sees": "admin",
}
GIF_FRAMES = [
    "home", "search-typo", "medicine-demo", "verify-manual", "gate-blocked", "comparison", "summary", "emergency",
]


def walk(suite):
    for spec in suite.get("specs", []):
        for test in spec["tests"]:
            yield spec["title"], test
    for child in suite.get("suites", []):
        yield from walk(child)


def collect_videos() -> int:
    VIDEOS.mkdir(parents=True, exist_ok=True)
    report = json.loads((RESULTS / "results.json").read_text())
    count = 0
    for suite in report["suites"]:
        for title, test in walk(suite):
            for key, name in FLOWS.items():
                if key not in title:
                    continue
                for result in test["results"]:
                    for attachment in result.get("attachments", []):
                        if attachment["name"] == "video" and Path(attachment.get("path", "")).exists():
                            shutil.copy(attachment["path"], VIDEOS / f"{test['projectName']}-{name}.webm")
                            count += 1
                            break
    return count


def build_gif() -> None:
    frames = []
    for name in GIF_FRAMES:
        path = SHOTS / f"desktop-{name}.png"
        if path.exists():
            with Image.open(path) as image:
                rgb = image.convert("RGB")
                # Screenshots are full page, so crop to the top and fit a consistent frame.
                cropped = rgb.crop((0, 0, rgb.width, min(rgb.height, 800)))
                canvas = Image.new("RGB", (rgb.width, 800), "white")
                canvas.paste(cropped, (0, 0))
                frames.append(canvas.resize((800, 500)).convert("P", palette=Image.Palette.ADAPTIVE, colors=128))
    frames[0].save(DEMO / "walkthrough.gif", save_all=True, append_images=frames[1:], duration=2200, loop=0, optimize=True)


if __name__ == "__main__":
    print(f"videos: {collect_videos()}")
    build_gif()
    print(f"gif: {(DEMO / 'walkthrough.gif').stat().st_size // 1024} kB")
