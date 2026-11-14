"""Arabic UI: one strings file (web/i18n/strings.json) for the web app and the API; every English key has Arabic."""
import json
import re
from dataclasses import replace
from pathlib import Path

import pytest

from godseye.config import load_config

ROOT = Path(__file__).resolve().parent.parent
STRINGS = json.loads((ROOT / "web" / "i18n" / "strings.json").read_text(encoding="utf-8"))
PLACEHOLDER = re.compile(r"\{(\w+)\}")
ARABIC_INDIC_DIGITS = re.compile("[٠-٩۰-۹]")


def test_every_english_key_has_an_arabic_string_with_the_same_placeholders():
    en, ar = STRINGS["en"], STRINGS["ar"]
    assert set(en) == set(ar), {"missing in ar": sorted(set(en) - set(ar)), "extra in ar": sorted(set(ar) - set(en))}
    for key, text in en.items():
        assert ar[key].strip(), f"empty Arabic string for {key}"
        assert set(PLACEHOLDER.findall(text)) == set(PLACEHOLDER.findall(ar[key])), key
        assert not ARABIC_INDIC_DIGITS.search(ar[key]), f"{key}: use Western digits"


def expand(prefix: str, values) -> set[str]:
    return {f"{prefix}{v}" for v in values}


def test_every_key_the_web_app_uses_exists():
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    used = set(re.findall(r'data-i18n(?:-aria)?="([^"]+)"', html))
    used |= set(re.findall(r'\bt\(\s*"(ui\.[^"]+)"', js))
    used |= set(re.findall(r'"(ui\.[a-z_.]+)"', js)) - {"ui.month."}       # keys picked with a ternary
    used |= expand("ui.view.", ["harmonized", "raw"]) | expand("ui.unit.", ["week", "day"])
    used |= expand("ui.per.", ["week", "day"]) | expand("ui.metric.", ["cell_days", "detections"])
    used |= expand("ui.metric_lc.", ["cell_days", "detections"]) | expand("ui.month.", range(1, 13))
    used |= expand("ui.rule.", ["default", "relative", "floor"])
    used |= expand("ui.level.", ["unusually low", "below usual", "about usual", "above usual", "unusually high"])
    used |= expand("ui.risk_level.", ["low", "moderate", "high", "very_high", "extreme"])
    assert used - set(STRINGS["en"]) == set()


def test_every_key_the_api_uses_exists():
    src = "".join(p.read_text(encoding="utf-8") for p in (ROOT / "src" / "godseye" / "api").glob("*.py"))
    used = set(re.findall(r'"(api\.[a-z_.]+[a-z_])"', src))
    used |= expand("api.note.", range(1, 7)) | expand("api.month.", range(1, 13))
    used |= expand("api.method.", ["identity", "global_ratio", "region_month_shrunk_ratio", "region_only"])
    used |= expand("api.level.", ["unusually low", "below usual", "about usual", "above usual", "unusually high"])
    used |= expand("api.aoi.", load_config(env={}).aois)                     # every named area has a label
    assert used - set(STRINGS["en"]) == set()


@pytest.fixture()
def client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from godseye.api import calendar as calendar_api
    from godseye.api import climatology as climatology_api
    from godseye.config import get_config
    from tests.test_climatology_api import multi_year_store

    calendar_api.STORE["calendar"] = multi_year_store()
    app = FastAPI()
    app.include_router(calendar_api.router)
    app.include_router(climatology_api.router)
    cfg = load_config(env={})
    app.dependency_overrides[get_config] = lambda: replace(cfg, climatology={"activity": "absolute"})
    try:
        with TestClient(app) as c:
            yield c
    finally:
        calendar_api.STORE.clear()


Q = {"aoi": "jordan", "series": "NOAA-20-VIIRS"}


def test_api_answers_in_arabic_with_western_digits_and_english_by_default(client):
    en = client.get("/api/calendar/critical-periods", params=Q).json()
    ar = client.get("/api/calendar/critical-periods", params={**Q, "lang": "ar"}).json()
    peak = en["periods"][0]["peak_week"]
    assert en["summary"] == STRINGS["en"]["api.all_year"].format(peak=peak)         # active all year (absolute rule)
    assert ar["summary"] == STRINGS["ar"]["api.all_year"].format(peak=f"\u2068{peak}\u2069")   # isolated number
    assert "\u2068" not in json.dumps(en, ensure_ascii=False)                  # English text has no isolates
    assert ar["aoi"]["label"] == STRINGS["ar"]["api.aoi.jordan"] and en["aoi"]["label"] == "Jordan"
    cal = client.get("/api/calendar", params={"aoi": "jordan", "lang": "ar"}).json()
    assert cal["notes"][0] == STRINGS["ar"]["api.note.1"]
    assert cal["metric_label"] == STRINGS["ar"]["api.metric.cell_days"]
    now = client.get("/api/calendar/now", params={**Q, "lang": "ar"}).json()
    assert "الأسبوع" in now["summary"]
    assert now["level"] in {"unusually low", "below usual", "about usual", "above usual", "unusually high"}   # a code
    for body in (ar, cal, now):
        assert not ARABIC_INDIC_DIGITS.search(json.dumps(body, ensure_ascii=False))
    assert client.get("/api/calendar", params={"aoi": "jordan", "lang": "fr"}).status_code == 422
