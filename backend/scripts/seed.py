"""Pre-ingest the synthetic contracts through the running API (for demo prep).

Usage:  python scripts/seed.py [--api http://localhost:8000] [--include-scanned]
"""
import argparse
import time
from pathlib import Path

import requests

MIME = {".pdf": "application/pdf", ".txt": "text/plain",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--include-scanned", action="store_true",
                    help="also ingest the image-only PDF (slow: vision OCR per page)")
    args = ap.parse_args()

    contracts_dir = Path(__file__).resolve().parents[2] / "data" / "contracts"
    files = sorted(contracts_dir.glob("0[12]_*.txt"))
    if args.include_scanned:
        files += sorted(contracts_dir.glob("03_*scanned*.pdf"))

    ids = []
    for f in files:
        with f.open("rb") as fh:
            r = requests.post(f"{args.api}/ingest",
                              files={"file": (f.name, fh, MIME.get(f.suffix, "application/octet-stream"))},
                              timeout=60)
        r.raise_for_status()
        cid = r.json()["contract_id"]
        ids.append((f.name, cid))
        print(f"queued {f.name} -> contract_id={cid}")

    print("\nwaiting for processing", end="", flush=True)
    pending = {cid for _, cid in ids}
    while pending:
        time.sleep(5)
        print(".", end="", flush=True)
        for cid in list(pending):
            status = requests.get(f"{args.api}/contracts/{cid}", timeout=30).json()["status"]
            if status in ("done", "failed"):
                pending.discard(cid)
                print(f"\n  {cid}: {status}")
    print("\nAll contracts processed:")
    for name, cid in ids:
        print(f"  {name}: {cid}")


if __name__ == "__main__":
    main()
