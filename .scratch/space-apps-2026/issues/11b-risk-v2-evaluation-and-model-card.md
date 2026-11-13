# 11b: Risk v2 evaluation suite + model card

**What to build:** `python -m godseye evaluate` scores v2 once on the test block and writes every number in the model card to `reports/`.

**Blocked by:** 11a

**Status:** done

- [x] ROC-AUC, PR-AUC, Brier; BSS vs persistence and vs "2026 frequency to date"; NOAA-20 climatology BSS only for AOIs with 2020–2025 archives
- [x] Reliability diagram + numpy Platt/isotonic, fitted on validation
- [x] New-activity subset; per-region metrics; 5° spatial blocks (cut candidate #3)
- [x] Risk-level thresholds from observed rates on validation
- [x] Gain importance
- [x] `docs/MODEL_CARD.md` with v1 as a comparison row; never "accuracy"

## Comments

- `godseye evaluate` (`risk/evaluate_suite.py`, `risk/calibration.py`) scores the test block once, writes `reports/risk_evaluation.json`, `reports/figures/risk_reliability.png` and `docs/MODEL_CARD.md`, and adds test scores and calibration to `models/risk_v2/model_meta.json`.
- **Test block 2026-10-02 to 10-30:**
  - Calibrated v2: ROC-AUC 0.867, PR-AUC 0.731, Brier 0.106. BSS +0.197 vs persistence and +0.365 vs 2026 frequency.
  - Persistence: 0.749 / 0.456 / 0.133.
  - Validation (0.904) was optimistic, as expected.
- **New-activity subset:** ROC-AUC 0.694, PR-AUC 0.150, BSS +0.089 vs persistence. Every region has BSS > 0 vs persistence (+0.12 to +0.28).
- **Calibration:** isotonic, fitted on validation; the observed test rate per level falls inside its band. Live forecasts are now calibrated.
- **Spatial 5° blocks:** 0.876 with lat/lon vs 0.871 without, so no place memorization. Lat/lon are kept.
