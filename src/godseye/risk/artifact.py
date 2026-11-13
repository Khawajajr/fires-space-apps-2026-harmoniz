"""
Risk-model artifacts: LightGBM's native text model plus a metadata JSON, instead of a pickle.

  <model_dir>/model.txt         the booster (gitignored)
  <model_dir>/model_meta.json   features, parameters, data window, data sha256, metrics, git SHA, created_at and the
                                fields the API serves (grid, horizon, risk bins); small, committed

A pickle can run code when loaded and ties the model to a Python version; the text model doesn't. The old v1 pickle
is migrated once (`migrate_pickle`); predictions are identical (checked by the contract test).
"""
from __future__ import annotations

import hashlib
import json
import pickle
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import lightgbm as lgb

MODEL = "model.txt"
META = "model_meta.json"


def file_sha256(path: Path) -> str | None:
    if not Path(path).exists():
        return None
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(1 << 24):
            h.update(chunk)
    return h.hexdigest()


def git_sha(root: Path) -> str | None:
    try:
        out = subprocess.run(["git", "-C", str(root), "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                             timeout=10)
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def save(bundle: dict, directory: Path, extra: dict | None = None) -> Path:
    """Write bundle["model"] as text and every other bundle field (plus `extra`) as metadata."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    bundle["model"].save_model(str(directory / MODEL))
    meta = {k: v for k, v in bundle.items() if k != "model"}
    meta.update(extra or {})
    meta.setdefault("created_at", datetime.now(timezone.utc).isoformat(timespec="seconds"))
    meta["num_trees"] = bundle["model"].num_trees()
    (directory / META).write_text(json.dumps(meta, indent=2, default=str) + "\n")
    return directory


def load(directory: Path) -> dict:
    """The bundle as the API and train code use it: {"model": Booster, **metadata}."""
    directory = Path(directory)
    meta = json.loads((directory / META).read_text())
    return {"model": lgb.Booster(model_file=str(directory / MODEL)), **meta}


def exists(directory: Path) -> bool:
    return (Path(directory) / MODEL).exists() and (Path(directory) / META).exists()


def read_meta(directory: Path) -> dict | None:
    path = Path(directory) / META
    return json.loads(path.read_text()) if path.exists() else None


def migrate_pickle(pkl: Path, directory: Path, data_path: Path | None, root: Path) -> Path:
    """One-time conversion of the v1 pickle bundle into the native artifact.

    v1's training provenance (data hash, code version, parameters, time) was never recorded, so those fields stay
    null; what we know at migration time is stored under migrated_*. If the committed metadata already exists (a
    fresh clone), only model.txt is restored and the tracked metadata is left untouched."""
    with open(pkl, "rb") as fh:
        bundle = pickle.load(fh)
    directory = Path(directory)
    if (directory / META).exists():
        directory.mkdir(parents=True, exist_ok=True)
        bundle["model"].save_model(str(directory / MODEL))
        return directory
    return save(bundle, directory, {
        "name": directory.name, "version": "v1", "created_at": None, "data_sha256": None, "git_sha": None,
        "params": None, "data_window": None,
        "migrated_from": Path(pkl).name, "migrated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "migrated_with_data_sha256": file_sha256(data_path) if data_path else None,
        "migrated_at_git_sha": git_sha(root),
        "note": "v1 was refit on train + validation after early stopping; its validation metrics are optimistic, and "
                "its training provenance was not recorded (see ticket 11a and ADR 0005).",
    })
