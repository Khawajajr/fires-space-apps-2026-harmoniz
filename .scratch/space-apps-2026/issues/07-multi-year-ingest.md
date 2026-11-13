# 07: Multi-year ingest for the Levant + Argentina archives

**What to build:** When the FIRMS archive downloads arrive, `ingest --aoi` reads them in place from `C:\Users\muham\Downloads\firms_archive\` and extends the per-sensor aggregates back to **2018-01-01** for these AOIs (or further, if earlier years are delivered later).

**Blocked by:** 03, and files appearing in `C:\Users\muham\Downloads\firms_archive\` (watched; start as soon as it has files)

**Status:** ready-for-agent

- [ ] `python -m godseye ingest --aoi levant|argentina|jordan` is idempotent; the originals are never moved or copied; outputs go under `data/`
- [ ] **Dedupe against the 2026 files already in `data/raw`:** archive beats NRT; same satellite + acquisition time + location = duplicate (one row kept). Counts of dropped duplicates are in the ingest report.
- [ ] Inventory of what arrived (file, satellite, archive/NRT, first/last date, rows) streamed in chunks; manifest updated (source, date range, rows, sha256)
- [ ] Sensor × year coverage chart in `reports/figures/`
- [ ] Ingest report: per AOI, years of history (expected 2018–2026 = 9, so the ADR 0006 ≥5-year rule passes), weeks per year passing each ADR 0006 gate, and which rule applies
- [ ] Records the earliest year per sensor, so 08 can pick its calibration window automatically

## Comments

From the 03 review, things 07 must handle:
- `availability()` assumes **global** input (zero detections worldwide = outage). AOI-only archives can't show that, because a fire-free AOI day is a real zero. For AOI archive years, take status from the sensor start/end dates plus the known global outage days we have (the 2026 table), and set `basis = "aoi_archive"` so the rule is visible. Never mark an AOI zero day as `no_data`.
- Set the manifest `source.url` to the real per-file origin (FIRMS archive request), not just the generic download page.
- Coverage chart: add a sensor × year view once the years exist.
