"""Configuration: configs/*.yaml plus environment overrides. The single source of truth for paths and constants."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class AOI:
    name: str
    label: str
    bbox: tuple[float, float, float, float]  # west, south, east, north


@dataclass(frozen=True)
class Sensor:
    name: str               # e.g. "Aqua-MODIS"
    satellite: str          # canonical satellite name written by `clean`, e.g. "Aqua"
    instrument: str         # MODIS | VIIRS
    start: date | None      # first day of FIRMS data; None = take it from the data
    end: date | None        # last day; None = still delivering


@dataclass(frozen=True)
class Config:
    root: Path
    display_name: str
    data_dir: Path
    models_dir: Path
    frontend_dir: Path
    web_dir: Path
    figures_dir: Path
    clean: dict
    risk: dict
    api: dict
    aggregate: dict = field(default_factory=dict)
    harmonize: dict = field(default_factory=dict)
    climatology: dict = field(default_factory=dict)
    risk_v2: dict = field(default_factory=dict)
    sensors: dict[str, Sensor] = field(default_factory=dict)
    aois: dict[str, AOI] = field(default_factory=dict)
    firms_map_key: str | None = None

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def processed_dir(self) -> Path:
        return self.data_dir / "processed"

    @property
    def model_dir(self) -> Path:
        return self.models_dir / self.risk["model_dir"]

    @property
    def legacy_model_path(self) -> Path:
        return self.models_dir / self.risk["legacy_model_file"]

    @property
    def predictions_path(self) -> Path:
        return self.processed_dir / self.risk["predictions_file"]


def load_config(config_dir: Path | None = None, env: dict | None = None) -> Config:
    env = os.environ if env is None else env
    config_dir = Path(config_dir or env.get("GODSEYE_CONFIG_DIR") or ROOT / "configs")
    root = config_dir.parent
    pipeline = yaml.safe_load((config_dir / "pipeline.yaml").read_text(encoding="utf-8"))
    aois_raw = yaml.safe_load((config_dir / "aois.yaml").read_text(encoding="utf-8")) or {}
    paths = pipeline["paths"]
    resolve = lambda p: (root / p).resolve()
    return Config(
        root=root,
        display_name=pipeline["display_name"],
        data_dir=Path(env["GODSEYE_DATA_DIR"]).resolve() if env.get("GODSEYE_DATA_DIR") else resolve(paths["data_dir"]),
        models_dir=resolve(paths["models_dir"]),
        frontend_dir=resolve(paths["frontend_dir"]),
        web_dir=resolve(paths["web_dir"]),
        figures_dir=resolve(paths["figures_dir"]),
        clean=pipeline["clean"],
        risk=pipeline["risk"],
        api=pipeline["api"],
        aggregate=pipeline["aggregate"],
        harmonize=pipeline["harmonize"],
        climatology=pipeline["climatology"],
        risk_v2=pipeline["risk_v2"],
        sensors={name: Sensor(name, s["satellite"], s["instrument"], s["start"], s["end"])
                 for name, s in pipeline["sensors"].items()},
        aois={name: AOI(name, a["label"], tuple(float(v) for v in a["bbox"])) for name, a in aois_raw.items()},
        firms_map_key=env.get("FIRMS_MAP_KEY") or None,
    )


@lru_cache(maxsize=1)
def get_config() -> Config:
    return load_config()
