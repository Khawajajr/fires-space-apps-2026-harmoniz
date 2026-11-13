# 01: Package skeleton (prefactor)

**What to build:** The prototype becomes an installable `godseye` package with one config source and a `python -m godseye <command>` CLI, with no behaviour change. The old scripts and the backend keep working as thin wrappers, and the four existing endpoints return the same JSON.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] `pip install -e .` works; the `sys.path` hack is gone
- [ ] Pipeline YAML + named-AOI YAML (jordan, levant, argentina) replace the hard-coded grid, horizon, bins and paths; env overrides for the data dir and the FIRMS key; display name "F.I.R.E.S." is one config value
- [ ] `python -m godseye clean|train|api` run the existing logic; `scripts/*.py` are thin wrappers
- [ ] Committed FIRMS fixture (a few hundred rows per sensor) covering the edge cases listed in the spec
- [ ] Seam 1 tests (`clean.harmonize_schema`) green
- [ ] Contract test: `/api/health`, `/api/fires/recent(.geojson)`, `/api/predictions/risk-map`, `/api/predictions/risk-at` return the same JSON as before
- [ ] `ruff` clean; pytest green
