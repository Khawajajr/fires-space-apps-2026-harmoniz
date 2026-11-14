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
    out = Path(args.out or cfg.models_dir / (cfg.risk_v2["v21_model_dir"] if args.climatology else
                                             cfg.risk_v2["model_dir"]))
    train_v2.run(cfg, Path(args.processed or cfg.processed_dir), out, args.n_estimators or cfg.risk_v2["n_estimators"],
                 args.climatology)


def _evaluate(args) -> None:
    from godseye.risk import evaluate_suite

    cfg = get_config()
    evaluate_suite.run(cfg, cfg.processed_dir, cfg.served_model_dir, cfg.root / "reports",
                       cfg.figures_dir, cfg.root / "docs" / "MODEL_CARD.md")


def _aggregate(args) -> None:
    from godseye.ingest import pipeline

    cfg = get_config()
    pipeline.run(cfg, Path(args.clean_dir or cfg.processed_dir), Path(args.out or cfg.processed_dir),
                 Path(args.figure or cfg.figures_dir / "coverage_sensor_date.png"))


def _ingest(args) -> None:
    from godseye.ingest import aoi

    cfg = get_config()
    aoi.run(cfg, args.aoi, Path(args.archive or cfg.archive_dir))


def _ingest_archive(args) -> None:
    from godseye.ingest import archive

    cfg = get_config()
    archive.run(cfg, Path(args.archive or cfg.archive_dir), args.workers, args.only, merge_parts=not args.no_merge)


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


def _demo(args) -> None:
    """Fresh-clone demo: build the committed FIRMS fixture into data/demo and serve the calendar app."""
    import os

    from godseye import config

    demo = config.ROOT / "data" / "demo"
    os.environ["GODSEYE_DATA_DIR"] = str(demo)
    config.get_config.cache_clear()
    cfg = get_config()
    fixture = cfg.root / "tests" / "fixtures" / "firms"
    from godseye.clean import pipeline as clean
    from godseye.ingest import pipeline as ingest

    clean.run([str(fixture)], cfg.processed_dir, min_confidence=cfg.clean["min_confidence"],
              grid_deg=cfg.clean["grid_deg"], recent_days=cfg.clean["recent_days"],
              table_format=cfg.clean["table_format"])
    ingest.run(cfg, cfg.processed_dir, cfg.processed_dir, demo / "coverage.png")
    print()
    print(f"Demo data in {demo}. Open http://{args.host}:{args.port}/app/ (fixture data: a few hundred detections; "
          "risk endpoints answer 503 because the demo has no trained model).")
    _api(args)


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
    t2.add_argument("--climatology", action="store_true",
                    help="v2.1: + the cell's NOAA-20 2019-2025 weekly climatology (needs ingest-archive)")
    t2.set_defaults(func=_train_v2)

    e = sub.add_parser("evaluate", help="score risk v2 once on the test block; write reports/ and docs/MODEL_CARD.md")
    e.set_defaults(func=_evaluate)

    g = sub.add_parser("aggregate", help="cleaned detections -> per-sensor fire cells, grid, availability, chart")
    g.add_argument("--clean-dir", help=f"directory holding fires_clean (default: {cfg.processed_dir})")
    g.add_argument("--out", help=f"output directory (default: {cfg.processed_dir})")
    g.add_argument("--figure", help=f"coverage chart path (default: {cfg.figures_dir / 'coverage_sensor_date.png'})")
    g.set_defaults(func=_aggregate)

    i = sub.add_parser("ingest", help="multi-year record for one AOI from the FIRMS archive downloads (ticket 07)")
    i.add_argument("--aoi", required=True, help="named AOI from configs/aois.yaml")
    i.add_argument("--archive", help=f"archive folder, read in place (default: {cfg.archive_dir})")
    i.set_defaults(func=_ingest)

    ia = sub.add_parser("ingest-archive", help="one pass over the global archive zips: AOI stores, calibration "
                                               "regions, availability, NOAA-20 climatology (ticket 07)")
    ia.add_argument("--archive", help=f"folder of FIRMS archive zips, read in place (default: {cfg.archive_dir})")
    ia.add_argument("--workers", type=int, help="parallel processes (default: cores - 1)")
    ia.add_argument("--only", nargs="*", help="zip file names to read (timing runs)")
    ia.add_argument("--no-merge", action="store_true", help="read zips into parts only")
    ia.set_defaults(func=_ingest_archive)

    m = sub.add_parser("manifest", help="record every FIRMS input file (source, dates, rows, sha256)")
    m.add_argument("inputs", nargs="*", help=f"files or directories (default: {cfg.raw_dir})")
    m.add_argument("--out", help=f"manifest path (default: {cfg.data_dir / 'manifest.json'})")
    m.set_defaults(func=_manifest)

    h = sub.add_parser("harmonize", help="fit the sensor links in configs/pipeline.yaml (cross-validated)")
    h.add_argument("--processed", help=f"sensor grid + availability directory (default: {cfg.processed_dir})")
    h.set_defaults(func=_harmonize)

    d = sub.add_parser("demo", help="fresh-clone demo: build the test fixture into data/demo and serve the app")
    d.add_argument("--host", default=cfg.api["host"])
    d.add_argument("--port", type=int, default=cfg.api["port"])
    d.add_argument("--reload", action="store_true")
    d.set_defaults(func=_demo)

    a = sub.add_parser("api", help="serve the HTTP API and the dashboard")
    a.add_argument("--host", default=cfg.api["host"])
    a.add_argument("--port", type=int, default=cfg.api["port"])
    a.add_argument("--reload", action="store_true")
    a.set_defaults(func=_api)
    return ap


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    args.func(args)
