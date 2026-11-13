import json

import pandas as pd

from godseye.cli import main


def test_clean_cli_on_the_fixture_writes_every_output(fixture_dir, tmp_path):
    main(["clean", str(fixture_dir), "--out", str(tmp_path)])

    report = json.loads((tmp_path / "cleaning_report.json").read_text())
    assert report["input_rows"] == 1615
    dropped = sum(v for k, v in report.items() if k.startswith("dropped_"))
    assert report["output_rows"] == report["input_rows"] - dropped
    assert set(report["output_by_satellite"]) == {"Terra", "Aqua", "Suomi-NPP", "NOAA-20", "NOAA-21"}

    clean = pd.read_feather(tmp_path / "fires_clean.feather")
    assert len(clean) == report["output_rows"]
    grid = pd.read_feather(tmp_path / "fires_daily_grid.feather")
    assert grid.n_detections.sum() == len(clean)
    assert (grid.n_modis + grid.n_viirs == grid.n_detections).all()
    assert (tmp_path / "fires_recent.feather").exists()
    geo = json.loads((tmp_path / "fires_recent.geojson").read_text())
    assert geo["type"] == "FeatureCollection" and geo["features"]


def test_clean_is_deterministic(fixture_dir, tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    main(["clean", str(fixture_dir), "--out", str(a)])
    main(["clean", str(fixture_dir), "--out", str(b)])
    read = lambda d: pd.read_feather(d / "fires_clean.feather")
    pd.testing.assert_frame_equal(read(a), read(b))
