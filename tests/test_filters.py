import pandas as pd

from godseye.clean.filters import global_filters, row_filters
from godseye.clean.schema import CATEGORICAL, compact, harmonize_schema
from tests.conftest import read_raw


def row_filtered(*names, report, min_conf="nominal"):
    """Same order as the pipeline: harmonize -> row filters -> compact per file, then concat as categoricals."""
    parts = [compact(row_filters(harmonize_schema(read_raw(n), n), min_conf, report)) for n in names]
    df = pd.concat(parts, ignore_index=True)
    for c in CATEGORICAL:
        df[c] = df[c].astype("category")
    return df


def test_row_filters_drop_zero_frp_and_below_minimum_confidence():
    report = {}
    out = row_filtered("edge_modis.csv", "edge_viirs_nrt.csv", report=report)
    assert report["dropped_frp_le_zero"] == 1
    assert report["dropped_confidence_below_nominal"] == 2  # MODIS 29 and VIIRS "l"
    assert (out.frp_mw > 0).all()
    assert set(out.confidence_class) <= {"nominal", "high"}


def test_global_filters_drop_static_types_and_nrt_rows_next_to_known_static_sources():
    report = {}
    df = row_filtered("edge_modis.csv", "edge_viirs_nrt.csv", report=report)
    out = global_filters(df, keep_static=False, report=report)
    assert report["dropped_non_vegetation_type"] == 3           # MODIS type 1, 2, 3
    assert report["dropped_nrt_near_known_static_source"] == 1  # NOAA-20 NRT row on the type-2 site
    assert not ((out.latitude == 26.5) & (out.longitude == 50.1)).any()


def test_keep_static_keeps_them():
    report = {}
    out = global_filters(row_filtered("edge_modis.csv", report=report), keep_static=True, report=report)
    assert set(out["type"].dropna()) >= {1, 2, 3}


def test_duplicates_are_dropped_once():
    report = {}
    df = row_filtered("edge_viirs_api.csv", "edge_viirs_api.csv", report=report)
    out = global_filters(df, keep_static=True, report=report)
    assert report["dropped_duplicates"] == 2
    assert len(out) == 2
