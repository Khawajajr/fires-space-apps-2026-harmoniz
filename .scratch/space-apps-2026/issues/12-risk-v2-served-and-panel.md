# 12: Risk v2 served + "Next 7 days" panel

**What to build:** The existing risk endpoints serve v2 with the same contract, and `web/` shows a "Next 7 days" risk panel for the selected AOI.

**Blocked by:** 04, 11a

**Status:** done (per-cell contributions deferred: cut candidate #2)

- [x] Risk endpoints serve v2; the contract test passes; the globe still works
- [x] `web/` panel: AOI risk summary + map layer, with the test-block metric and its baseline beside it
- [ ] Per-cell contributions via `pred_contrib` (cut candidate #2)

## Comments

- `risk.serve: v2` in `configs/pipeline.yaml` (v1 remains one line away).
- The risk endpoints keep v0's exact shape:
  - a new golden schema test covers all 10 contract cases;
  - value fingerprints for the 5 risk cases apply only while v1 is served.
- `/api/health` exposes v2's metrics with v1's keys (test scores once 11b has run, else validation). `/api/meta` shows the served model.
- Web "Next 7 days":
  - counts per risk level and the top cells;
  - the metric next to persistence, stating which block it comes from;
  - the scope note, and an optional map layer of the top 1,500 cells.
- Per-cell contributions (`pred_contrib`) are not done: cut candidate #2, revisit if time remains.
