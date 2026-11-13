# 01: Package skeleton (prefactor)

**What to build:** The prototype becomes an installable `godseye` package with one config source and a `python -m godseye <command>` CLI, with no behaviour change. The old scripts and the backend keep working as thin wrappers, and the four existing endpoints return the same JSON.

**Blocked by:** None (can start immediately)

**Status:** done

- [x] `pip install -e .` works; the `sys.path` hack is gone
- [x] Pipeline YAML + named-AOI YAML (jordan, levant, argentina) replace the hard-coded grid, horizon, bins and paths; env overrides for the data dir and the FIRMS key; display name "F.I.R.E.S." is one config value
- [x] `python -m godseye clean|train|api` run the existing logic; `scripts/*.py` are thin wrappers
- [x] Committed FIRMS fixture (a few hundred rows per sensor) covering the edge cases listed in the spec
- [x] Seam 1 tests (`clean.harmonize_schema`) green
- [x] Contract test: `/api/health`, `/api/fires/recent(.geojson)`, `/api/predictions/risk-map`, `/api/predictions/risk-at` return the same JSON as before
- [x] `ruff` clean; pytest green

## Comments

- Contract test verified locally (11/11 match golden.json from the v0-prototype server; live `godseye api` server too).
  It is skipped in CI and on fresh clones (no real data). Retraining via the old wrapper reproduced the model JSON and
  predictions exactly.
- Deliberate small changes: readers now prefer feather (ADR 0002), the API title is "F.I.R.E.S. API" 0.2.0, error hints name
  `godseye clean|train`, `clean` with no inputs reads `data/raw`, and `requirements.txt` became `requirements.lock`.
- Review follow-ups moved to 02 (see there).
