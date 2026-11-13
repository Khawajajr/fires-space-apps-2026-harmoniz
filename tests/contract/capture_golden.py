"""Record fingerprints of a running API (default: the v0-prototype backend on :8000).

    python -m tests.contract.capture_golden [base_url]
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

from tests.contract.cases import CASES, FILE_CASES, file_fingerprint, fingerprint

GOLDEN = Path(__file__).with_name("golden.json")


def main(base: str = "http://127.0.0.1:8000") -> None:
    out = {}
    for path in CASES + FILE_CASES:
        with urllib.request.urlopen(base + path, timeout=300) as r:
            body = r.read()
        out[path] = (file_fingerprint if path in FILE_CASES else fingerprint)(body)
        print(f"{out[path][:12]}  {path}")
    GOLDEN.write_text(json.dumps(out, indent=2) + "\n")


if __name__ == "__main__":
    main(*sys.argv[1:])
