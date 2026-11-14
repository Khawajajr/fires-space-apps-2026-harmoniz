"""The four prototype endpoints must return exactly what v0-prototype returned (golden.json, captured from it).

Needs the real processed data and model; skipped where they don't exist (CI, fresh clones).
"""
import json
from pathlib import Path

import pytest

from godseye.config import get_config
from tests.contract.cases import CASES, FILE_CASES, RISK_LEVELS, file_fingerprint, fingerprint, schema

GOLDEN = json.loads(Path(__file__).with_name("golden.json").read_text())
GOLDEN_SCHEMA = json.loads(Path(__file__).with_name("golden_schema.json").read_text())
RISK = ("/api/health", "/api/predictions/")
CFG = get_config()
pytestmark = pytest.mark.skipif(
    not ((CFG.processed_dir / "fires_recent.feather").exists()
         and ((CFG.model_dir / "model.txt").exists() or CFG.legacy_model_path.exists())),
    reason="real processed data / model not present")


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from godseye.api.app import app

    with TestClient(app) as c:
        yield c


@pytest.mark.parametrize("path", CASES + FILE_CASES)
def test_response_matches_v0_prototype(client, path):
    """Exact values. Risk answers change when a new model is served, so those are pinned only while v1 is served."""
    if path.startswith(RISK) and CFG.risk.get("serve") != "v1":
        pytest.skip("a newer model is served: risk values differ by design; the schema test still applies")
    r = client.get(path)
    assert r.status_code == 200
    got = (file_fingerprint if path in FILE_CASES else fingerprint)(r.content)
    assert got == GOLDEN[path]


@pytest.mark.parametrize("path", CASES)
def test_response_shape_matches_v0_prototype(client, path):
    """Same keys and value types as v0 for every endpoint, whichever model is served (the globe depends on them)."""
    r = client.get(path)
    assert r.status_code == 200
    assert schema(r.json()) == normalize(GOLDEN_SCHEMA[path])


def normalize(shape):
    """Apply schema()'s risk-level rule to a stored shape."""
    if isinstance(shape, dict):
        if shape and set(shape) <= RISK_LEVELS:
            return {"<level>": normalize(next(iter(shape.values())))}
        return {k: normalize(v) for k, v in shape.items()}
    return [normalize(x) for x in shape] if isinstance(shape, list) else shape


def test_meta_describes_data_model_and_attribution(client):
    m = client.get("/api/meta").json()
    assert m["name"] == CFG.display_name and "FIRMS" in m["attribution"][0]
    assert {s["sensor"] for s in m["sensors"]} >= {"Aqua-MODIS", "NOAA-20-VIIRS"}
    assert m["model"]["version"] == CFG.risk.get("serve", "v1") and m["model"]["num_trees"] > 0


def test_meta_reports_each_stores_date_range(client):
    m = client.get("/api/meta").json()
    stores = {s["name"]: s for s in m["stores"]}
    assert stores["global"]["kind"] == "global"
    assert m["data_range"] == [min(s["first_day"] for s in m["stores"]), max(s["last_day"] for s in m["stores"])]
    for s in m["stores"]:
        if s["kind"] == "aoi":                                 # multi-year AOI stores reach back before the global one
            assert s["first_day"] <= stores["global"]["first_day"] and s["bbox"] is not None
