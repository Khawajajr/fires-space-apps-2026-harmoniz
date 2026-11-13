# F.I.R.E.S. — NASA Space Apps 2026

Entry for "Harmonization of MODIS and VIIRS Hot Spots". Mission brief: `CLAUDE_CODE_PROMPT.md`.
Display name lives in one config value; the Python package stays `godseye` (internal).

## Run
- Backend: `.venv\Scripts\python -m uvicorn backend.main:app --port 8000` → `curl localhost:8000/api/health`
- Leaflet dashboard: served by the backend at `http://localhost:8000/`
- Globe: `cd gods-eye-view; npm run dev` → `http://localhost:4173` (needs `GODS_EYE_API_URL=http://127.0.0.1:8000`)
- Pipeline: `.venv\Scripts\python scripts\clean_fire_data.py` (~7 min), then `scripts\train_model.py` (~25 s)
- Globe tests: `cd gods-eye-view; npm test`. One known failure, not ours: `src/tooling/nominatimOutlineRoute.test.mjs:687`
  ("the disk cache survives a restart…", Windows file permissions). Don't edit upstream tests to fix it.

## Repos
- `gods_eye/` (this repo, branch `main`, tag `v0-prototype`). `gods-eye-view/` is ignored here.
- `gods-eye-view/` is a separate clone of bilawalsidhu/gods-eye-view (MIT). Our work is on branch `space-apps-2026`.
  Keep upstream licence and notices.

## Windows / Smart App Control
- Python 3.14 venv. Before adding any compiled dep (geopandas, shapely, sklearn, numba…) run
  `python -c "import X"` and drop it if it fails. Prefer numpy/pandas.
- Use feather/zstd for tables (ADR 002); parquet and scipy.stats import today but have been blocked before.
- Use the native LightGBM API, not the sklearn wrapper.

## Data
- `data/raw/DL_FIRE_{M-C61,SV-C2,J1V-C2,J2V-C2}_83967x`: global, 2026-01-01 → 2026-11-06 only (S-NPP ends 11-02).
  Archive to 07-31 (VIIRS) / 08-31 (MODIS), NRT after. Satellite codes are Aqua/Terra/SNPP/N20/N21; the SV-C2
  `instrument` column says "SNPP"; VIIRS NRT has no `type` column.
- Never commit data or model binaries. Read the originals in place; write outputs under `data/`.

## Non-negotiables
- Never break the running demo; keep old entry points working until the new ones are tested.
- Never add MODIS and VIIRS counts or FRP and call it "fires". Keep per-sensor series; harmonized = estimate ± band.
- Missing data ≠ zero fire: make cloud, orbit gaps, outages and the S-NPP end explicit.
- Every reported metric is reproducible by one command and is shown next to its baseline. Never call ROC-AUC "accuracy".
- No leakage: time-ordered splits, horizon gaps, spatial-block checks.
- Credit everything in `docs/REFERENCES.md` (datasets, libs, gods-eye-view, Gemini, Claude, Matt Pocock skills).
- English everywhere. Small commits; run the tests before each one. Ask before deleting, force-pushing or anything irreversible.
- Log progress in `docs/CHANGELOG_HACKATHON.md`.
