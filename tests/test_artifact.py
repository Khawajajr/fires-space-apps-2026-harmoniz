"""Ticket 02: native model artifact (text model + metadata) and the one-time pickle migration."""
import json
import pickle

import lightgbm as lgb
import numpy as np
import pytest

from godseye.config import ROOT
from godseye.risk import artifact


@pytest.fixture(scope="module")
def booster():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(400, 3))
    y = (X[:, 0] + rng.normal(scale=0.5, size=400) > 0).astype(int)
    return lgb.train({"objective": "binary", "verbosity": -1}, lgb.Dataset(X, y), num_boost_round=10), X


def test_round_trip_predicts_identically(booster, tmp_path):
    model, X = booster
    artifact.save({"model": model, "features": ["a", "b", "c"], "grid_deg": 0.25}, tmp_path / "m", {"version": "t"})
    back = artifact.load(tmp_path / "m")
    assert np.array_equal(back["model"].predict(X), model.predict(X))
    assert back["features"] == ["a", "b", "c"] and back["version"] == "t" and back["num_trees"] == 10
    assert "created_at" in back and artifact.exists(tmp_path / "m")


def test_pickle_is_migrated_once_with_provenance(booster, tmp_path):
    model, X = booster
    pkl = tmp_path / "old.pkl"
    with open(pkl, "wb") as fh:
        pickle.dump({"model": model, "features": ["a", "b", "c"], "validation": [{"model": "LightGBM"}]}, fh)
    data = tmp_path / "grid.feather"
    data.write_bytes(b"grid")
    artifact.migrate_pickle(pkl, tmp_path / "risk_v1", data, ROOT)
    meta = json.loads((tmp_path / "risk_v1" / artifact.META).read_text())
    assert meta["migrated_from"] == "old.pkl" and meta["version"] == "v1"
    assert meta["data_sha256"] is None and meta["git_sha"] is None and meta["created_at"] is None   # unknown for v1
    assert len(meta["migrated_with_data_sha256"]) == 64 and "optimistic" in meta["note"]
    assert np.array_equal(artifact.load(tmp_path / "risk_v1")["model"].predict(X), model.predict(X))


def test_fresh_clone_restores_the_model_without_rewriting_tracked_metadata(booster, tmp_path):
    model, X = booster
    pkl = tmp_path / "old.pkl"
    with open(pkl, "wb") as fh:
        pickle.dump({"model": model, "features": ["a"]}, fh)
    artifact.migrate_pickle(pkl, tmp_path / "m", None, ROOT)
    before = (tmp_path / "m" / artifact.META).read_text()
    (tmp_path / "m" / artifact.MODEL).unlink()                 # a clone has the meta (committed), not model.txt
    artifact.migrate_pickle(pkl, tmp_path / "m", None, ROOT)
    assert (tmp_path / "m" / artifact.META).read_text() == before and artifact.exists(tmp_path / "m")
