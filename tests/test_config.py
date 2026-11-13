from pathlib import Path

from godseye.config import ROOT, load_config


def test_defaults_come_from_the_yaml():
    cfg = load_config(env={})
    assert cfg.display_name == "F.I.R.E.S."
    assert cfg.processed_dir == (ROOT / "data" / "processed").resolve()
    assert cfg.risk["horizon_days"] == 7
    assert cfg.clean["table_format"] == "feather"
    assert cfg.firms_map_key is None


def test_env_overrides_data_dir_and_map_key(tmp_path):
    cfg = load_config(env={"GODSEYE_DATA_DIR": str(tmp_path), "FIRMS_MAP_KEY": "abc"})
    assert cfg.raw_dir == Path(tmp_path).resolve() / "raw"
    assert cfg.firms_map_key == "abc"


def test_named_aois():
    aois = load_config(env={}).aois
    assert {"jordan", "levant", "argentina"} <= set(aois)
    west, south, east, north = aois["argentina"].bbox
    assert west < east and south < north
