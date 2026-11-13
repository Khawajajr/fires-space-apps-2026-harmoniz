# 02: Native model artifact + /api/meta

**What to build:** The risk model is stored as LightGBM's native text model plus a metadata JSON instead of a pickle, and the API reports which data and which model it is serving.

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] Native model text + metadata (features, params, data window, data hash, metrics, git SHA, created_at)
- [ ] One-time loader migrates the old pickle
- [ ] `GET /api/meta`: dataset coverage per sensor, model version, attribution (pydantic model)
- [ ] Contract test for the existing endpoints still green

## Comments

Follow-ups from the 01 review (judgement calls; fold in where 02 touches the code anyway):
- Typed config sections (dataclasses) instead of `cfg.risk["..."]` string keys; stop freezing config at import time
  (`HORIZON_DAYS`, `RISK_BINS`) so `load_config(env=...)` is a real seam for tests.
- `grid_deg` appears under both `clean` and `risk` in pipeline.yaml; there should be one value, or a check that they agree.
- The API decides VIIRS vs MODIS from `sensor_res_m`, while the schema decides it from the satellite: use one rule.
- The GeoJSON point builder is duplicated (`clean.io.write_geojson` and `/api/fires/recent`).
