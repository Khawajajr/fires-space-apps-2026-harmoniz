# 11a: Risk v2: NOAA-20 label/features, 3 blocks, train

**What to build:** A v2 risk model trained from scratch with the NOAA-20 reference label and features (ADR 0004) on the three time-ordered blocks (ADR 0005), saved as a native artifact.

**Blocked by:** 02, 03

**Status:** ready-for-agent

- [ ] Label: ≥1 NOAA-20 fire cell-day in the 0.25° cell in t+1..t+7; VIIRS features from NOAA-20 only; the MODIS-only brightness feature is dropped
- [ ] Blocks: train ≤ 2026-08-21, validation 08-28..09-25 (early stopping), test 10-02..10-30 untouched
- [ ] No warm start from v1
- [ ] Seam 4 tests: metrics vs hand-computed values; leakage guards (no label window crosses a block boundary)
- [ ] One command trains the model and writes the artifact + metadata
