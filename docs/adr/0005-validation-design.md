# Risk model validation: three time-ordered blocks separated by the horizon

v1 picked the number of trees on the same 6 weeks it reported metrics on, and the shipped model was refit on all labels, so its numbers are optimistic. v2 uses weekly issue dates split into three blocks, each separated by the 7-day horizon so no label window crosses a boundary (2026 global data, last labelled issue date 2026-10-30):

- **train:** issue dates ≤ 2026-08-21
- **validation:** 2026-08-28 → 2026-09-25 (5 dates): early stopping, calibration, risk thresholds
- **test:** 2026-10-02 → 2026-10-30 (5 dates): scored once at the end; every reported number comes from here

A spatial-block check over 5° blocks guards against memorizing places. v2 is trained from scratch; warm-starting from v1 would leak the test block.

Baselines: persistence everywhere. The global data is 2026 only, so the global test block uses a **"2026 frequency to date"** baseline (not called climatology). True NOAA-20 2020–2025 climatology skill is reported only for AOIs whose archives were ingested; if none were, the model card says so.
