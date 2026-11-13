"""The four prototype endpoints must return exactly what v0-prototype returned (golden.json, captured from it).

Needs the real processed data and model; skipped where they don't exist (CI, fresh clones).
"""
import json
from pathlib import Path

import pytest

from godseye.config import get_config
from tests.contract.cases import CASES, FILE_CASES, file_fingerprint, fingerprint

GOLDEN = json.loads(Path(__file__).with_name("golden.json").read_text())
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
    r = client.get(path)
    assert r.status_code == 200
    got = (file_fingerprint if path in FILE_CASES else fingerprint)(r.content)
    assert got == GOLDEN[path]


def test_meta_describes_data_model_and_attribution(client):
    m = client.get("/api/meta").json()
    assert m["name"] == CFG.display_name and "FIRMS" in m["attribution"][0]
    assert {s["sensor"] for s in m["sensors"]} >= {"Aqua-MODIS", "NOAA-20-VIIRS"}
    assert m["model"]["version"] == "v1" and m["model"]["num_trees"] > 0
