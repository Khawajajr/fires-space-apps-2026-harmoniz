"""Seam 1: clean.harmonize_schema, raw FIRMS rows in, unified rows out."""
import numpy as np
import pandas as pd
import pytest

from godseye.clean import harmonize_schema
from godseye.clean.schema import UNIFIED_COLUMNS
from tests.conftest import FIXTURE_DIR, read_raw


@pytest.mark.parametrize("path", sorted(FIXTURE_DIR.glob("*.csv")), ids=lambda p: p.name)
def test_every_fixture_file_maps_onto_the_unified_schema(path):
    out = harmonize_schema(pd.read_csv(path, dtype=str), path.name)
    assert list(out.columns) == UNIFIED_COLUMNS
    assert out.acq_datetime.notna().all()
    assert set(out.instrument) <= {"MODIS", "VIIRS"}
    assert set(out.satellite) <= {"Terra", "Aqua", "Suomi-NPP", "NOAA-20", "NOAA-21"}
    assert (out.sensor_res_m == np.where(out.instrument == "VIIRS", 375, 1000)).all()


def test_unpadded_acq_time_is_read_as_hhmm_utc():
    out = harmonize_schema(read_raw("edge_modis.csv"), "edge")
    assert [t.strftime("%H:%M") for t in out.acq_datetime[:4]] == ["00:05", "00:45", "09:45", "10:30"]
    assert str(out.acq_datetime.dt.tz) == "UTC"


def test_modis_confidence_classes_follow_the_c61_thresholds():
    out = harmonize_schema(read_raw("edge_modis.csv"), "edge")
    assert out.confidence_class[:4].tolist() == ["low", "nominal", "nominal", "high"]
    assert out.confidence_pct[:4].tolist() == [29, 30, 79, 80]


def test_viirs_letter_confidence_and_satellite_codes():
    out = harmonize_schema(read_raw("edge_viirs_nrt.csv"), "edge")
    assert out.confidence_class[:3].tolist() == ["low", "nominal", "high"]
    assert out.confidence_pct.isna().all()
    # S-NPP files put "SNPP" in the instrument column; the instrument is decided from the satellite.
    assert out.satellite[:3].tolist() == ["Suomi-NPP", "NOAA-20", "NOAA-21"]
    assert (out.instrument == "VIIRS").all()


def test_viirs_nrt_has_no_type_column_and_is_flagged_nrt():
    out = harmonize_schema(read_raw("edge_viirs_nrt.csv"), "edge")
    assert out["type"].isna().all()
    assert (out["product"] == "nrt").all()


def test_archive_versions_are_archive_and_type_is_kept():
    out = harmonize_schema(read_raw("edge_modis.csv"), "edge")
    assert (out["product"] == "archive").all()
    assert out["type"].tolist()[4:7] == [1, 2, 3]


def test_api_spelling_bright_ti4_and_single_letter_satellites():
    out = harmonize_schema(read_raw("edge_viirs_api.csv"), "edge")
    assert out.satellite.tolist() == ["Suomi-NPP", "NOAA-20"]
    assert out.brightness_k.tolist() == [335.5, 336.5]
    assert out.bright_t31_k.tolist() == [290.5, 291.5]
