"""data/manifest.json: every FIRMS input file with its source, date range, rows and sha256.

Entries are reused while a file's size and mtime are unchanged, so re-running is cheap and idempotent.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

from godseye.clean.io import iter_csvs

FIRMS_DOWNLOAD_URL = "https://firms.modaps.eosdis.nasa.gov/download/"


def sha256(path: Path, block: int = 1 << 24) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(block):
            h.update(chunk)
    return h.hexdigest()


def describe(path: Path) -> dict:
    """Stream one CSV/zip: rows, first/last acq_date, satellites, archive vs NRT versions."""
    rows, first, last, satellites, versions = 0, None, None, Counter(), Counter()
    for _, chunk in iter_csvs([str(path)], usecols=["acq_date", "satellite", "version"]):
        rows += len(chunk)
        lo, hi = chunk.acq_date.min(), chunk.acq_date.max()
        first = lo if first is None or lo < first else first
        last = hi if last is None or hi > last else last
        satellites.update(chunk.satellite.value_counts().to_dict())
        versions.update(chunk.version.value_counts().to_dict())
    return {"rows": rows, "first_date": first, "last_date": last, "satellites": dict(sorted(satellites.items())),
            "product": sorted({"nrt" if "NRT" in v.upper() else "archive" for v in versions}),
            "versions": dict(sorted(versions.items()))}


def _display_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def build_manifest(inputs: list[Path], root: Path, previous: dict | None = None) -> dict:
    cached = {e["path"]: e for e in (previous or {}).get("files", [])}
    files = []
    for path in sorted(p for d in inputs for p in (Path(d).rglob("*") if Path(d).is_dir() else [Path(d)])
                       if p.suffix.lower() in (".csv", ".zip")):
        stat = path.stat()
        key = _display_path(path, root)
        old = cached.get(key)
        if old and old["bytes"] == stat.st_size and old["mtime_ns"] == stat.st_mtime_ns:
            files.append(old)
            continue
        entry = {"path": key, "bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns, "sha256": sha256(path),
                 "source": {"provider": "NASA FIRMS", "url": FIRMS_DOWNLOAD_URL,
                            "request": path.parent.name if path.parent.name.startswith("DL_FIRE_") else None}}
        entry.update(describe(path))
        files.append(entry)
        print(f"  {key}: {entry['rows']:,} rows {entry['first_date']} -> {entry['last_date']}")
    return {"files": files}


def write_manifest(inputs: list[Path], path: Path, root: Path) -> dict:
    previous = json.loads(path.read_text()) if path.exists() else None
    manifest = build_manifest(inputs, root, previous)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest
