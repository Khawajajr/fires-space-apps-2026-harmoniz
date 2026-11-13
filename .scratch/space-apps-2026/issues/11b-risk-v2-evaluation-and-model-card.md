# 11b: Risk v2 evaluation suite + model card

**What to build:** `python -m godseye evaluate` scores v2 once on the test block and writes every number in the model card to `reports/`.

**Blocked by:** 11a

**Status:** ready-for-agent

- [ ] ROC-AUC, PR-AUC, Brier; BSS vs persistence and vs "2026 frequency to date"; NOAA-20 climatology BSS only for AOIs with 2020–2025 archives
- [ ] Reliability diagram + numpy Platt/isotonic, fitted on validation
- [ ] New-activity subset; per-region metrics; 5° spatial blocks (cut candidate #3)
- [ ] Risk-level thresholds from observed rates on validation
- [ ] Gain importance
- [ ] `docs/MODEL_CARD.md` with v1 as a comparison row; never "accuracy"
