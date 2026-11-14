"""Static snapshot (site/): the file names the builder writes are the ones web/snapshot.js asks for."""
import re
from pathlib import Path

from godseye.site import file_for, js_number

ROOT = Path(__file__).resolve().parent.parent


def test_file_names_sort_the_query_and_match_what_the_browser_sends():
    assert file_for("calendar", {"unit": "week", "aoi": "levant", "lang": "ar", "metric": "cell_days"}) == \
        "data/api/calendar/aoi=levant&lang=ar&metric=cell_days&unit=week.json"
    assert file_for("meta", {}) == "data/api/meta/index.json"
    assert [js_number(v) for v in (32.0, 35.5, -60.75, 0.0)] == ["32", "35.5", "-60.75", "0"]   # String(x) in JS


def test_snapshot_js_builds_the_same_names_and_refuses_drawn_boxes():
    js = (ROOT / "web" / "snapshot.js").read_text(encoding="utf-8")
    assert "keys.map((k) => `${k}=${u.searchParams.get(k)}`).join(\"&\") || \"index\"" in js
    assert "data/api/${endpoint}/${encodeURIComponent(query)}.json" in js
    assert re.search(r'drawn: u\.searchParams\.has\("bbox"\) && endpoint !== "predictions/risk-map"', js)
    assert 'src="snapshot.js"' not in (ROOT / "web" / "index.html").read_text(encoding="utf-8")   # live app: never
