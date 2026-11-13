# 11a: Risk v2: NOAA-20 label/features, 3 blocks, train

**What to build:** A v2 risk model trained from scratch with the NOAA-20 reference label and features (ADR 0004) on the three time-ordered blocks (ADR 0005), saved as a native artifact.

**Blocked by:** 02, 03

**Status:** done

- [x] Label: ≥1 NOAA-20 fire cell-day in the 0.25° cell in t+1..t+7; VIIRS features from NOAA-20 only; the MODIS-only brightness feature is dropped
- [x] Blocks: train ≤ 2026-08-21, validation 08-28..09-25 (early stopping), test 10-02..10-30 untouched
- [x] No warm start from v1
- [x] Seam 4 tests: metrics vs hand-computed values; leakage guards (no label window crosses a block boundary)
- [x] One command trains the model and writes the artifact + metadata

## Comments

- `risk/v2.py` (PanelV2, issue_blocks with separation checks, build), `risk/evaluate.py` (seam 4: scores, Brier skill), `risk/train_v2.py`, `godseye train-v2` (config `risk_v2`).
- Features: 21, all from NOAA-20. Fire cells replace detections where it matters; there's a night share and a coverage-gap feature (NOAA-20 gap days in the last 7). Dropped: the MODIS-only brightness feature, and FRP max (not kept in the sensor grid). Climatological probability and years since activity need multi-year data (07), so they're added later if it lands.
- Early stopping on validation picks 123 trees; the model is then trained on the train block only (no refit on validation, no warm start).
- Validation (not test): ROC-AUC 0.904, PR-AUC 0.800, Brier 0.093. Persistence: 0.782 / 0.511 / 0.162; 2026 frequency to date: 0.756 / 0.491 / 0.177. `test_scored: false` in the metadata.
- Artifact: `models/risk_v2/` (model.txt ignored; model_meta.json committed, with blocks, label, data sha256, git SHA).
- Review fixes:
  - **`gap_days_7` no longer sees the future:** outages only; the 'partial' flag uses a centred window.
  - **Season features dropped:** with one year they are a time index, and validation/test lie outside the training months. They return with multi-year data. Validation is unchanged without them.
  - Issue dates whose label window has a NOAA-20 outage are left out.
  - Issue dates are anchored on the configured test end.
  - Guard on grid dates.
