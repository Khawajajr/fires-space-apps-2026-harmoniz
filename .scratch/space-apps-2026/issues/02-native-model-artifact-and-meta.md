# 02: Native model artifact + /api/meta

**What to build:** The risk model is stored as LightGBM's native text model plus a metadata JSON instead of a pickle, and the API reports which data and which model it is serving.

**Blocked by:** 01

**Status:** done

- [x] Native model text + metadata (features, params, data window, data hash, metrics, git SHA, created_at)
- [x] One-time loader migrates the old pickle
- [x] `GET /api/meta`: dataset coverage per sensor, model version, attribution (pydantic model)
- [x] Contract test for the existing endpoints still green

## Comments

Follow-ups from the 01 review (judgement calls; fold in where 02 touches the code anyway):
- Typed config sections (dataclasses) instead of `cfg.risk["..."]` string keys; stop freezing config at import time
  (`HORIZON_DAYS`, `RISK_BINS`) so `load_config(env=...)` is a real seam for tests.
- `grid_deg` appears under both `clean` and `risk` in pipeline.yaml; there should be one value, or a check that they agree.
- The API decides VIIRS vs MODIS from `sensor_res_m`, while the schema decides it from the satellite: use one rule.
- The GeoJSON point builder is duplicated (`clean.io.write_geojson` and `/api/fires/recent`).
- From the 03 review: `Config.aggregate` is another string-keyed dict (make it typed with the rest); `Sensor.instrument` is now a third VIIRS/MODIS source, so derive `schema.VIIRS_SATELLITES` from `cfg.sensors`; the manifest library code prints (move printing to the CLI).

## Done (2026-11-14)

- `risk/artifact.py`: `model.txt` (LightGBM text; gitignored) + `model_meta.json` (features, params, data window, data sha256, git SHA, created_at, metrics, issue dates; committed).
- `train` writes it directly. The v1 pickle is migrated once at API startup into `models/risk_v1/` and records that v1's metrics are optimistic. The text round trip predicts identically (max diff 0.0), and the 11 contract cases are unchanged.
- `GET /api/meta`: name, data range, per-sensor first/last day and days by status, model provenance, harmonization links (method in words, provisional) and attribution.
- Follow-ups from 01/03 not done (typed config sections, a single VIIRS/MODIS rule, the duplicated GeoJSON builder): judgement calls, left for after the deadline.
- Review fixes: honest migration provenance (training fields null, migrated_* recorded), /api/meta reads the metadata file (no race), a fresh clone restores model.txt without rewriting tracked metadata.
