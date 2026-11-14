"""
The global multi-year calendar for any drawn box: 0.25° sensor-grid tiles (10° x 10°, 2012-2026) loaded lazily.

A request's box reads only the tiles it touches and keeps only the cells inside it, so memory follows the box, not the
globe. Built stores are kept in a small LRU cache. A box whose cells would exceed `max_rows` is refused (None), and the
caller falls back to the global 2026 store, so a continent-sized box can't exhaust memory.
"""
from __future__ import annotations

import threading
from collections import OrderedDict
from pathlib import Path

import numpy as np
import pandas as pd

from godseye.calendar.store import CalendarStore, grid_cells, in_bbox
from godseye.ingest.archive import TILE_DEG, tile_name

COLUMNS = ["sensor", "acq_date", "cell_lat", "cell_lon", "n_detections", "n_fire_cells"]


def tiles_for(bbox: tuple[float, float, float, float], deg: float = TILE_DEG) -> list[str]:
    """Tile ids a box touches (west > east crosses the antimeridian)."""
    w, s, e, n = bbox
    lats = np.arange(np.floor(max(s, -90) / deg) * deg, min(n, 89.999), deg)
    spans = [(w, e)] if w <= e else [(w, 180.0), (-180.0, e)]
    lons = np.concatenate([np.arange(np.floor(a / deg) * deg, min(b, 179.999), deg) for a, b in spans])
    la, lo = np.meshgrid(lats + deg / 2, lons + deg / 2)
    return sorted({str(t) for t in tile_name(la.ravel(), lo.ravel(), deg)})


class TileStores:
    def __init__(self, tile_dir: Path, avail: pd.DataFrame, grid_deg: float, chain=None, cache: int = 8,
                 max_rows: int = 30_000_000):
        self.dir, self.avail, self.grid_deg, self.chain = Path(tile_dir), avail, grid_deg, chain
        self.cache_size, self.max_rows = cache, max_rows
        self.available = {p.stem for p in self.dir.glob("t_*.feather")}
        self.first, self.last = pd.Timestamp(avail.acq_date.min()), pd.Timestamp(avail.acq_date.max())
        self._stores: OrderedDict = OrderedDict()
        self._refused: set = set()            # boxes over max_rows, remembered so they don't re-read tiles
        self._lock = threading.Lock()

    def too_large(self, bbox: tuple[float, float, float, float]) -> bool:
        """True when the box was refused for having more than max_rows (call after store_for)."""
        cells, snapped = grid_cells(bbox, self.grid_deg)
        return cells > 0 and tuple(snapped) in self._refused

    def store_for(self, bbox: tuple[float, float, float, float]) -> CalendarStore | None:
        cells, snapped = grid_cells(bbox, self.grid_deg)
        if cells == 0:
            return None
        key = tuple(snapped)
        with self._lock:
            if key in self._refused:
                return None
            if key in self._stores:
                self._stores.move_to_end(key)
                return self._stores[key]
            frames, rows = [], 0
            for name in tiles_for(bbox):
                if name not in self.available:
                    continue
                t = pd.read_feather(self.dir / f"{name}.feather", columns=COLUMNS)
                t = t[in_bbox(t.cell_lat.to_numpy(), t.cell_lon.to_numpy(), bbox)]
                rows += len(t)
                if rows > self.max_rows:
                    self._refused.add(key)
                    return None
                frames.append(t)
            grid = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
                {c: pd.Series(dtype=self.avail.sensor.dtype if c == "sensor" else float) for c in COLUMNS})
            if not len(grid):
                grid["acq_date"] = pd.Series(dtype="datetime64[s]")
            store = CalendarStore(grid, self.avail, self.grid_deg)   # no fire in the box: zero where data is ok
            store.attach_chain(self.chain)
            self._stores[key] = store
            while len(self._stores) > self.cache_size:
                self._stores.popitem(last=False)
            return store
