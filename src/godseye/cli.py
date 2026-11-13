"""`python -m godseye <command>`: one entry point for every pipeline step. Defaults come from configs/."""
from __future__ import annotations

import argparse
from pathlib import Path

from godseye.clean.schema import CONF_RANK
from godseye.config import get_config


def _clean(args) -> None:
    from godseye.clean import pipeline

    cfg = get_config()
    pipeline.run(args.inputs or [str(cfg.raw_dir)], Path(args.out or cfg.processed_dir),
                 min_confidence=args.min_confidence, grid_deg=args.grid_deg, recent_days=args.recent_days,
                 keep_static=args.keep_static, chunk_rows=cfg.clean["chunk_rows"],
                 table_format=cfg.clean["table_format"])


def _train(args) -> None:
    from godseye.risk import train

    cfg = get_config()
    train.run(grid_path=args.grid, out=args.out or cfg.model_dir,
              predictions=args.predictions or cfg.predictions_path, grid_deg=args.grid_deg, step=args.step,
              val_weeks=args.val_weeks, n_estimators=args.n_estimators,
              min_history_days=cfg.risk["min_history_days"])


def _train_v2(args) -> None:
    from godseye.risk import train_v2

    cfg = get_config()
    out = Path(args.out or cfg.models_dir / cfg.risk_v2["model_dir"])
    train_v2.run(cfg, Path(args.processed or cfg.processed_dir), out, args.n_estimators or cfg.risk_v2["n_estimators"])


def _aggregate(args) -> None:
    from godseye.ingest import pipeline

    cfg = get_config()
    pipeline.run(cfg, Path(args.clean_dir or cfg.processed_dir), Path(args.out or cfg.processed_dir),
                 Path(args.figure or cfg.figures_dir / "coverage_sensor_date.png"))


def _manifest(args) -> None:
    from godseye.ingest.manifest import write_manifest

    cfg = get_config()
    out = Path(args.out or cfg.data_dir / "manifest.json")
    m = write_manifest([Path(p) for p in (args.inputs or [cfg.raw_dir])], out, cfg.root)
    print(f"  wrote {out}: {len(m['files'])} files, {sum(f['rows'] for f in m['files']):,} rows")


def _harmonize(args) -> None:
    from godseye.harmonize import pipeline

    cfg = get_config()
    pipeline.run(cfg, Path(args.processed or cfg.processed_dir), cfg.root / "reports")


def _api(args) -> None:
    import uvicorn

    uvicorn.run("godseye.api.app:app", host=args.host, port=args.port, reload=args.reload)


def build_parser() -> argparse.ArgumentParser:
    cfg = get_config()
    ap = argparse.ArgumentParser(prog="godseye", description=f"{cfg.display_name} pipeline")
    sub = ap.add_subparsers(dest="command", required=True)

    c = sub.add_parser("clean", help="FIRMS CSV/zip downloads -> unified, filtered tables")
    c.add_argument("inputs", nargs="*", help=f"FIRMS CSV files, zips, or directories (default: {cfg.raw_dir})")
    c.add_argument("--out", help=f"output directory (default: {cfg.processed_dir})")
    c.add_argument("--min-confidence", choices=list(CONF_RANK), default=cfg.clean["min_confidence"])
    c.add_argument("--grid-deg", type=float, default=cfg.clean["grid_deg"])
    c.add_argument("--recent-days", type=int, default=cfg.clean["recent_days"])
    c.add_argument("--keep-static", action="store_true", help="keep volcano/industrial/offshore detections")
    c.set_defaults(func=_clean)

    t = sub.add_parser("train", help="train the 7-day risk model on fires_daily_grid")
    t.add_argument("--grid", type=Path)
    t.add_argument("--out", type=Path, help=f"model directory: model.txt + model_meta.json (default: {cfg.model_dir})")
    t.add_argument("--predictions", type=Path, help=f"latest forecast CSV (default: {cfg.predictions_path})")
    t.add_argument("--grid-deg", type=float, default=cfg.risk["grid_deg"])
    t.add_argument("--step", type=int, default=cfg.risk["step_days"], help="days between training issue dates")
    t.add_argument("--val-weeks", type=int, default=cfg.risk["val_weeks"], help="most recent issue dates held out")
    t.add_argument("--n-estimators", type=int, default=cfg.risk["n_estimators"])
    t.set_defaults(func=_train)

    t2 = sub.add_parser("train-v2", help="train risk model v2 (NOAA-20 label, train/validation/test blocks)")
    t2.add_argument("--processed", help="directory with the sensor grid and availability")
    t2.add_argument("--out", help="model directory (default: models/<risk_v2.model_dir>)")
    t2.add_argument("--n-estimators", type=int)
    t2.set_defaults(func=_train_v2)

    g = sub.add_parser("aggregate", help="cleaned detections -> per-sensor fire cells, grid, availability, chart")
    g.add_argument("--clean-dir", help=f"directory holding fires_clean (default: {cfg.processed_dir})")
    g.add_argument("--out", help=f"output directory (default: {cfg.processed_dir})")
    g.add_argument("--figure", help=f"coverage chart path (default: {cfg.figures_dir / 'coverage_sensor_date.png'})")
    g.set_defaults(func=_aggregate)

    m = sub.add_parser("manifest", help="record every FIRMS input file (source, dates, rows, sha256)")
    m.add_argument("inputs", nargs="*", help=f"files or directories (default: {cfg.raw_dir})")
    m.add_argument("--out", help=f"manifest path (default: {cfg.data_dir / 'manifest.json'})")
    m.set_defaults(func=_manifest)

    h = sub.add_parser("harmonize", help="fit the sensor links in configs/pipeline.yaml (cross-validated)")
    h.add_argument("--processed", help=f"sensor grid + availability directory (default: {cfg.processed_dir})")
    h.set_defaults(func=_harmonize)

    a = sub.add_parser("api", help="serve the HTTP API and the dashboard")
    a.add_argument("--host", default=cfg.api["host"])
    a.add_argument("--port", type=int, default=cfg.api["port"])
    a.add_argument("--reload", action="store_true")
    a.set_defaults(func=_api)
    return ap


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    args.func(args)
