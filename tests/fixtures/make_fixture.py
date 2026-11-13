"""Rebuild the committed FIRMS test fixture.

    python tests/fixtures/make_fixture.py [raw_dir]

Takes the first and last ROWS rows of every FIRMS CSV under raw_dir (2026 global downloads), so every sensor
appears in both its archive and NRT form, then adds hand-written edge cases. FIRMS data is public domain.
"""
from __future__ import annotations

import sys
from collections import deque
from pathlib import Path

HERE = Path(__file__).parent / "firms"
ROWS = 100

MODIS_HEADER = ("latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,instrument,confidence,"
                "version,bright_t31,frp,daynight,type")
EDGE_MODIS = [
    # unpadded acq_time; confidence 29/30/79/80 boundaries; type 1 (volcano), 2 (static), 3 (offshore)
    "31.95,35.93,320.1,1.0,1.0,2026-07-01,5,Aqua,MODIS,29,61.03,300.0,10.5,D,0",
    "31.96,35.94,321.1,1.0,1.0,2026-07-01,45,Aqua,MODIS,30,61.03,300.0,11.5,D,0",
    "31.97,35.95,322.1,1.0,1.0,2026-07-01,945,Terra,MODIS,79,61.03,300.0,12.5,D,0",
    "31.98,35.96,323.1,1.0,1.0,2026-07-01,1030,Terra,MODIS,80,61.03,300.0,13.5,D,0",
    "37.75,14.99,350.0,1.0,1.0,2026-07-01,1100,Aqua,MODIS,90,61.03,300.0,50.0,D,1",
    "26.50,50.10,340.0,1.0,1.0,2026-07-01,1100,Aqua,MODIS,90,61.03,300.0,40.0,D,2",
    "28.00,49.00,330.0,1.0,1.0,2026-07-01,1100,Aqua,MODIS,90,61.03,300.0,30.0,N,3",
    # zero FRP; antimeridian longitudes
    "-16.50,179.95,310.0,1.0,1.0,2026-07-02,2200,Aqua,MODIS,70,61.03,290.0,0.0,N,0",
    "-16.60,-179.95,311.0,1.0,1.0,2026-07-02,2200,Aqua,MODIS,70,61.03,290.0,5.0,N,0",
]
VIIRS_NRT_HEADER = ("latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,instrument,confidence,"
                    "version,bright_t31,frp,daynight")
EDGE_VIIRS_NRT = [
    # S-NPP says "SNPP" in instrument; l/n/h confidence; NRT version; no type column; one row near the static source
    "31.95,35.93,330.1,0.4,0.4,2026-08-03,7,SNPP,SNPP,l,2.0NRT,295.0,1.2,D",
    "31.95,35.93,331.1,0.4,0.4,2026-08-03,1107,N20,VIIRS,n,2.0NRT,295.0,2.2,D",
    "31.95,35.93,332.1,0.4,0.4,2026-08-03,1157,N21,VIIRS,h,2.0NRT,295.0,3.2,D",
    "26.50,50.10,340.0,0.4,0.4,2026-08-03,1200,N20,VIIRS,h,2.0NRT,295.0,8.0,D",
]
VIIRS_API_HEADER = ("latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,"
                    "version,bright_ti5,frp,daynight")
EDGE_VIIRS_API = [
    # API spelling: bright_ti4 / bright_ti5, single-letter satellite codes
    "-34.60,-58.38,335.5,0.39,0.36,2026-08-04,0412,N,VIIRS,nominal,2.0NRT,290.5,4.4,N",
    "-34.61,-58.39,336.5,0.39,0.36,2026-08-04,0502,1,VIIRS,high,2.0NRT,291.5,5.4,N",
]


def head_tail(path: Path, n: int) -> tuple[str, list[str]]:
    with open(path, encoding="utf-8") as fh:
        header = fh.readline().rstrip("\n")
        head = [next(fh).rstrip("\n") for _ in range(n)]
        tail = deque((line.rstrip("\n") for line in fh), maxlen=n)
    return header, head + list(tail)


def write(path: Path, header: str, rows: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join([header, *rows]) + "\n", encoding="utf-8")


def main(raw_dir: str = "data/raw") -> None:
    for src in sorted(Path(raw_dir).glob("DL_FIRE_*/*.csv")):
        header, rows = head_tail(src, ROWS)
        product = src.stem.split("_")[1]                   # archive | nrt
        sensor = src.parent.name.split("_")[2]             # M-C61 | SV-C2 | J1V-C2 | J2V-C2
        write(HERE / f"fire_{product}_{sensor}_fixture.csv", header, rows)
    write(HERE / "edge_modis.csv", MODIS_HEADER, EDGE_MODIS)
    write(HERE / "edge_viirs_nrt.csv", VIIRS_NRT_HEADER, EDGE_VIIRS_NRT)
    write(HERE / "edge_viirs_api.csv", VIIRS_API_HEADER, EDGE_VIIRS_API)
    for p in sorted(HERE.glob("*.csv")):
        print(f"{p.name}: {sum(1 for _ in open(p)) - 1} rows")


if __name__ == "__main__":
    main(*sys.argv[1:])
