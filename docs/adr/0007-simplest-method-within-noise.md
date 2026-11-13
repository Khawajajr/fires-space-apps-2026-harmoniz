# Harmonization method: the simplest one that isn't beaten out of sample

For each sensor link we compare four mappings out of sample (leave one month out; one year out once there are several years): no correction, one global ratio, region x month ratios shrunk towards their parents, and quantile mapping per region x season. We ship the **simplest** method whose region-month error (WAPE) is within **2% (relative)** of the best. A more complex method must win by more than noise, because a complex method that wins by chance makes every downstream number harder to explain and to trust.

First result, 2026 overlap, fire cell-days on days both sensors delivered full data:
- **NOAA-20 → S-NPP: no correction.** The sensors agree within 1% (global ratio 0.993, 90% CI 0.983–1.001, resampling whole months). No correction ties the global ratio within noise (region-month WAPE 0.0317 vs 0.0322), so the simpler one ships.
- **NOAA-21 → S-NPP: global ratio 1.027** (90% CI 1.021–1.031). This halves the weekly global error compared with no correction.
- Both are sensitive to which days count as full data. Without the cross-sensor check the ratios are about 1.4% lower, because partial S-NPP deliveries pull them down. That is recorded as a caveat in the report.
- Regional and quantile methods lost: they fit noise.

## Consequences

- The same rule chooses the VIIRS → Aqua-equivalent link (tickets 06 and 08), where real regional differences are more likely.
- Calibrating on "full data" days needed a better availability check. On days when S-NPP lost granules, it delivered as little as 39% of NOAA-20's fires while staying above the global 20%-of-median rule. So VIIRS sensor-days are now also marked partial when they fall short of the other VIIRS satellites (see `aggregate.cross_sensor_fraction`). MODIS is excluded from that check, because Terra and Aqua pass at different times of day.
