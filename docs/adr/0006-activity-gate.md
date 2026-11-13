# Activity gate for anomalies and critical periods, fixed before seeing the data

A week counts toward anomalies and critical periods only if it passes the AOI's activity gate. These rules were fixed before any AOI's multi-year data was looked at, so they can't be tuned to the results:

1. **Default:** the week's climatological probability of any activity is ≥ 10%.
2. **Relative:** if fewer than 8 weeks per year pass the default gate for an AOI, use the AOI's top 20% of weeks by activity probability instead. The unit stays weekly, so every AOI's calendar has the same shape.
3. **Floor:** if the AOI averages < 1 Aqua-equivalent fire cell-day per week over its record, no gate is applied and no critical periods are defined. The UI shows "too little detected activity to define critical periods". The calendar and anomalies (vs p90 / z ≥ 2) are still shown.

The ingest report prints, per AOI, the number of weeks per year that pass each gate and which rule was applied.
