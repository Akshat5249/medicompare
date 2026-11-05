"""Run one OCR engine over the dataset and store raw spans, so scoring can be repeated without OCR.

Run: python evaluation/run_ocr.py --engine rapidocr --workers 3
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OMP_THREAD_LIMIT", "1")

from app.prescriptions import imaging  # noqa: E402
from app.prescriptions.ocr import get_engine  # noqa: E402


def recognise(task: tuple[str, str]) -> dict:
    engine_name, path = task
    engine = get_engine(engine_name)
    data = Path(path).read_bytes()
    started = time.perf_counter()
    processed = imaging.preprocess(data)
    prep_done = time.perf_counter()
    spans = engine.recognize(processed)
    finished = time.perf_counter()
    return {
        "id": Path(path).stem,
        "spans": [{"text": s.text, "bbox": list(s.bbox), "quality": s.quality} for s in spans],
        "preprocess_ms": round((prep_done - started) * 1000, 1),
        "ocr_ms": round((finished - prep_done) * 1000, 1),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", required=True, choices=["tesseract", "rapidocr"])
    parser.add_argument("--dataset", type=Path, default=ROOT / "evaluation/datasets/v1")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--splits", default="validation,test,train")
    args = parser.parse_args()
    paths = [p for split in args.splits.split(",") for p in sorted((args.dataset / split).glob("*.png"))]
    out = ROOT / "evaluation/results" / f"raw_{args.engine}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    engine = get_engine(args.engine)
    version = engine.version
    started = time.perf_counter()
    with Pool(args.workers) as pool, open(out, "w", encoding="utf-8") as handle:
        for done, result in enumerate(pool.imap_unordered(recognise, [(args.engine, str(p)) for p in paths], chunksize=4), 1):
            handle.write(json.dumps(result, ensure_ascii=False) + "\n")
            if done % 50 == 0:
                print(f"{args.engine}: {done}/{len(paths)} in {time.perf_counter() - started:.0f}s", flush=True)
    (ROOT / "evaluation/results" / f"raw_{args.engine}.meta.json").write_text(
        json.dumps({"engine": args.engine, "version": version, "images": len(paths), "workers": args.workers})
    )
    print(f"{args.engine} done: {len(paths)} images in {time.perf_counter() - started:.0f}s", flush=True)


if __name__ == "__main__":
    main()
