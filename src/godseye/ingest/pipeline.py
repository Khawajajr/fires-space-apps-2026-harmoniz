"""`godseye aggregate`: cleaned detections -> per-sensor fire cells, sensor grid, availability, coverage chart."""
from __future__ import annotations

import time
from pathlib import Path

from godseye.clean.io import read_table, write_table
from godseye.config import Config
from godseye.ingest.aggregate import availability, fire_cells, sensor_grid
from godseye.ingest.coverage import plot_coverage

COLUMNS = ["satellite", "acq_date", "latitude", "longitude", "frp_mw", "daynight"]


def run(cfg: Config, clean_dir: Path, out_dir: Path, figure: Path) -> dict:
    t0 = time.time()
    det = read_table(clean_dir, "fires_clean", COLUMNS)
    fine, coarse = cfg.aggregate["fine_deg"], cfg.clean["grid_deg"]
    cells = fire_cells(det, cfg.sensors, fine)
    del det
    grid = sensor_grid(cells, fine, coarse)
    avail = availability(cells, cfg.sensors, cfg.aggregate["partial_fraction"])
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = [write_table(cells, out_dir / "sensor_fire_cells", "feather"),
             write_table(grid, out_dir / "sensor_grid_daily", "feather"),
             write_table(avail, out_dir / "sensor_availability", "feather"),
             plot_coverage(avail, figure, f"{cfg.display_name}: FIRMS coverage by sensor (global, {fine}° fire cells)")]
    summary = {
        "fire_cell_days": {str(k): int(v) for k, v in cells.groupby("sensor", observed=True).size().items()},
        "status_days": {f"{s}/{st}": int(n) for (s, st), n in
                        avail.groupby(["sensor", "status"], observed=True).size().items()},
    }
    for p in paths:
        print(f"  wrote {p}  ({p.stat().st_size / 1e6:.1f} MB)")
    print(f"  fire cell-days per sensor: {summary['fire_cell_days']}")
    print(f"  not-ok sensor-days: { {k: v for k, v in summary['status_days'].items() if not k.endswith('/ok')} }")
    print(f"  [{time.time() - t0:.0f}s]")
    return summary
