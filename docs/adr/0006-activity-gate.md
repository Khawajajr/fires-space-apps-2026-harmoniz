# Activity gate for anomalies and critical periods, fixed before seeing the data

A week counts toward anomalies and critical periods only if it passes the AOI's activity gate. These rules were fixed before any AOI's multi-year data was looked at, so they can't be tuned to the results:

1. **Default:** the week's climatological probability of any activity is ≥ 10%.
2. **Relative:** if fewer than 8 weeks per year pass the default gate for an AOI, use the AOI's top 20% of weeks by activity probability instead. The unit stays weekly, so every AOI's calendar has the same shape.
3. **Floor:** if the AOI averages < 1 Aqua-equivalent fire cell-day per week over its record, no gate is applied and no critical periods are defined. The UI shows "too little detected activity to define critical periods". The calendar and anomalies (vs p90 / z ≥ 2) are still shown.

The ingest report prints, per AOI, the number of weeks per year that pass each gate and which rule was applied.

**History minimum (applies before rules 1–3):** climatology, anomalies and critical periods need at least **5 years** of history for the AOI. Below that, those panels show "needs ≥5 years of history (currently N)" rather than a climatology built from one or two years. The calendar itself is always shown.

**Amendment: what "activity" means (status: ACCEPTED, 2026-11-14, by the team).**
Ticket 09's synthetic tests showed that the original definition, "any activity" = ≥ 1 fire cell-day, makes almost every week of a large AOI active. Stray background detections happen year-round, so the default gate passes and the critical period becomes the whole year. A week is therefore active when it reaches **10% of the AOI's own peak weekly median** (never below 1 fire cell-day). This is scale-invariant and follows the usual fire-season definitions. It **changes the meaning of rule 1**; rules 2 and 3 are unchanged.

**Still fixed in advance.** The team accepted this on Sat 14 Nov 2026, before any multi-year AOI data had been merged or looked at. The global archive zips were still being read, and no climatology, anomaly or critical period had been computed on real multi-year data. The evidence came only from synthetic data (ticket 09), so the rule can't have been tuned to the results.
It is set by `climatology.activity: relative` in `configs/pipeline.yaml`; `absolute` restores the original definition for comparison.
