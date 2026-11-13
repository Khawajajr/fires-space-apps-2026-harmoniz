"""Detection filters: per-row validity checks, then global (static source, archive-vs-NRT, duplicate) checks."""
from __future__ import annotations

import numpy as np
import pandas as pd

from godseye.clean.schema import CONF_RANK, WILDFIRE_TYPE


def row_filters(df: pd.DataFrame, min_conf: str, report: dict) -> pd.DataFrame:
    """Per-row checks that need no global context; applied chunk by chunk."""
    def drop(mask, reason):
        nonlocal df
        report[reason] = report.get(reason, 0) + int(mask.sum())
        df = df[~mask]

    drop(df[["latitude", "longitude", "acq_datetime", "frp_mw", "confidence_class"]].isna().any(axis=1),
         "dropped_missing_core_fields")
    drop(~df.latitude.between(-90, 90) | ~df.longitude.between(-180, 180), "dropped_bad_coords")
    drop(df.frp_mw <= 0, "dropped_frp_le_zero")
    drop(df.confidence_class.map(CONF_RANK) < CONF_RANK[min_conf], f"dropped_confidence_below_{min_conf}")
    return df


def cell_key(lat: pd.Series, lon: pd.Series, deg: float) -> np.ndarray:
    return (np.floor(lat.to_numpy() / deg).astype(np.int64) * 100_000
            + np.floor(lon.to_numpy() / deg).astype(np.int64))


def static_source_mask(df: pd.DataFrame, cell_deg: float = 0.02) -> np.ndarray:
    """
    NRT files have no `type` column. Flag NRT detections that fall in ~2 km cells
    where the archive has labelled volcanoes / static industrial sources (type 1-2),
    so gas flares and steel plants do not leak into wildfire training data.
    Heuristic: it only knows sources seen in the archive period.
    """
    static = df["type"].isin([1, 2]).to_numpy()
    if not static.any():
        return np.zeros(len(df), dtype=bool)
    keys = cell_key(df.latitude, df.longitude, cell_deg)
    return df["type"].isna().to_numpy() & np.isin(keys, np.unique(keys[static]))


def global_filters(df: pd.DataFrame, keep_static: bool, report: dict) -> pd.DataFrame:
    def drop(mask, reason):
        nonlocal df
        mask = np.asarray(mask, dtype=bool)
        report[reason] = int(mask.sum())
        df = df[~mask]

    if not keep_static:
        near_static = static_source_mask(df)  # must run while archive type 1-2 rows still exist
        non_veg = (df["type"].notna() & (df["type"] != WILDFIRE_TYPE)).to_numpy(dtype=bool, na_value=False)
        report["dropped_non_vegetation_type"] = int(non_veg.sum())
        report["dropped_nrt_near_known_static_source"] = int(near_static.sum())
        df = df[~(non_veg | near_static)]

    # When archive and NRT overlap for a satellite-day, the archive (standard, reprocessed) wins.
    day_key = df.satellite.cat.codes.to_numpy().astype(np.int64) * 100_000 + df.acq_date.cat.codes.to_numpy()
    is_nrt = (df["product"] == "nrt").to_numpy()
    drop(is_nrt & np.isin(day_key, np.unique(day_key[~is_nrt])), "dropped_nrt_superseded_by_archive")

    drop(df.duplicated(["satellite", "acq_datetime", "latitude", "longitude"]), "dropped_duplicates")
    return df
