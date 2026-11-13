"""Requests whose JSON must not change across refactors, and how a response is fingerprinted."""
from __future__ import annotations

import hashlib
import json

CASES = [
    "/api/health",
    "/api/fires/recent",
    "/api/fires/recent?format=firms&hours=24&min_confidence=nominal&limit=200000",
    "/api/fires/recent?bbox=170,-60,-170,60&hours=168",
    "/api/fires/recent?instrument=MODIS&min_confidence=high&limit=500",
    "/api/fires/recent?instrument=VIIRS&bbox=34,29,42.5,37.5&hours=168",
    "/api/predictions/risk-map?min_risk=0.02",
    "/api/predictions/risk-map?format=geojson&bbox=34,29,42.5,37.5",
    "/api/predictions/risk-at?lat=-24&lon=31.5&radius_km=50&top=5",
    "/api/predictions/risk-at?lat=31.95&lon=35.93",
]
# Served from disk as-is: compare raw bytes.
FILE_CASES = ["/api/fires/recent.geojson"]


def fingerprint(body: bytes) -> str:
    """sha256 of canonical JSON, so key order and whitespace don't matter but every value does."""
    canonical = json.dumps(json.loads(body), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def file_fingerprint(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()
