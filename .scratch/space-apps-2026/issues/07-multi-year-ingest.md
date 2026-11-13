# 07: Multi-year ingest for the Levant + Argentina archives

**What to build:** When the FIRMS archive downloads arrive, `ingest --aoi` reads them in place and extends the per-sensor aggregates back to 2000 (MODIS) and 2012 (VIIRS) for these AOIs.

**Blocked by:** 03, and delivery of the 8 FIRMS archive requests

**Status:** ready-for-agent

- [ ] `python -m godseye ingest --aoi levant|argentina|jordan` is idempotent; the originals are never moved or copied
- [ ] Manifest updated (source URL, date range, rows, sha256)
- [ ] Sensor × year coverage chart in `reports/figures/`
- [ ] Ingest report: per AOI, years of history, weeks per year that pass each ADR 0006 gate, and which rule applies
