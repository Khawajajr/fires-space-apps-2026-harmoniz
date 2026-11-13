"""Reading FIRMS downloads (CSV, zip, directory) in chunks and writing tables."""
from __future__ import annotations

import importlib
import json
import zipfile
from pathlib import Path

import pandas as pd


def _importable(module: str) -> bool:
    # Actually import: on Smart App Control machines pyarrow is installed but a DLL can be blocked.
    try:
        importlib.import_module(module)
        return True
    except ImportError:
        return False


def resolve_table_format(preferred: str) -> str:
    """The configured format if this machine can write it, else the next safest one."""
    if preferred == "parquet" and _importable("pyarrow.parquet"):
        return "parquet"
    if preferred in ("parquet", "feather") and _importable("pyarrow.feather"):
        return "feather"
    return "csv"


def iter_csvs(paths: list[str], chunk_rows: int = 1_000_000):
    """Yield (name, chunk) for every CSV chunk in the given files/dirs/zips."""
    read = lambda src: pd.read_csv(src, dtype=str, chunksize=chunk_rows)
    for p in map(Path, paths):
        if p.is_dir():
            yield from iter_csvs([str(x) for x in sorted(p.rglob("*")) if x.suffix.lower() in (".csv", ".zip")],
                                 chunk_rows)
        elif p.suffix.lower() == ".zip":
            with zipfile.ZipFile(p) as zf:
                for n in zf.namelist():
                    if n.lower().endswith(".csv"):
                        with zf.open(n) as fh:
                            for chunk in read(fh):
                                yield f"{p.name}!{n}", chunk
        elif p.suffix.lower() == ".csv":
            for chunk in read(p):
                yield p.name, chunk


def write_table(df: pd.DataFrame, path_stem: Path, table_format: str) -> Path:
    if table_format == "parquet":
        path = path_stem.with_suffix(".parquet")
        df.to_parquet(path, index=False)
    elif table_format == "feather":
        path = path_stem.with_suffix(".feather")
        df.reset_index(drop=True).to_feather(path, compression="zstd")
    else:
        path = path_stem.with_suffix(".csv.gz")
        out = df.copy()
        if "acq_datetime" in out:
            out["acq_datetime"] = out["acq_datetime"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        out.to_csv(path, index=False, compression="gzip")
    return path


# ADR 0002: feather is the project format; csv.gz and parquet are read only as fallbacks from older runs.
READERS = {".feather": pd.read_feather, ".csv.gz": pd.read_csv, ".parquet": pd.read_parquet}


def find_table(directory: Path, stem: str) -> Path:
    for suffix in READERS:
        if (directory / f"{stem}{suffix}").exists():
            return directory / f"{stem}{suffix}"
    raise FileNotFoundError(f"{stem}{{{','.join(READERS)}}} not found in {directory} - run `godseye clean`")


def read_table_file(path: Path) -> pd.DataFrame:
    suffix = ".csv.gz" if path.name.endswith(".csv.gz") else path.suffix
    return READERS.get(suffix, pd.read_csv)(path)


def read_table(directory: Path, stem: str) -> pd.DataFrame:
    return read_table_file(find_table(directory, stem))


def write_geojson(recent: pd.DataFrame, path: Path) -> None:
    """Slim point FeatureCollection; 5-decimal coords (~1 m) keep the file small for the browser."""
    feats = [
        {"type": "Feature",
         "geometry": {"type": "Point", "coordinates": [lon, lat]},
         "properties": {"t": t, "frp": frp, "conf": c, "sat": s, "res": int(r), "dn": dn}}
        for lon, lat, t, frp, c, s, r, dn in zip(
            recent.longitude, recent.latitude, recent.acq_datetime.dt.strftime("%Y-%m-%dT%H:%MZ"),
            recent.frp_mw.astype(float), recent.confidence_class, recent.satellite,
            recent.sensor_res_m, recent.daynight)
    ]
    path.write_text(json.dumps({"type": "FeatureCollection", "features": feats}, separators=(",", ":")))
