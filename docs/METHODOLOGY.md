# Methodology

## 1. One scale across sensors (ADR 0001)

The headline is **Aqua-equivalent fire cell-days**: what Aqua-MODIS would have counted at its original ~13:30 afternoon overpass.

- **Why fire cell-days:** counting 0.01° (~1 km) cells with any detection, instead of detections, removes most of the pixel-size effect. A 1 km MODIS pixel and the four or more 375 m VIIRS pixels covering the same fire become one cell.
- **Why Aqua:** it has the longest afternoon record, and mapping the finer sensor down to the coarser one does not invent detail.
- **Which value is shown when:**
  - before 2003: no headline value ("no data"). Aqua starts on 2002-07-04, so 2003 is its first full year;
  - while Aqua's orbit was stable (2003–2021), Aqua observed;
  - after that, an estimate from VIIRS: S-NPP when it delivered full data that day, else NOAA-20/21 through their continuity links.
- **Excluded from the headline:** Terra (morning orbit), shown separately in "By sensor" from 2000-11-01.
  - We tested whether a Terra → Aqua link could carry the headline back to 2000–2002. The test was the same leave-one-year-out test as the other links, over 2003–2021 (19 folds).
  - The rule was fixed before running it: the band must cover 88–95% of held-out region-weeks, and region-month WAPE must be no worse than the shipped headline link's (0.086).
  - Result: band coverage 91.4% passes, but the best method (shrunk region × month ratios) reaches WAPE 0.136 (one global ratio: 0.459). It fails, so Terra stays per sensor. The likely reason is the overpass time: morning (~10:30) against afternoon (~13:30) changes how much of the day's burning each satellite sees, region by region.
- **Headline figure:** the naive record uses Aqua raw to 2011 and switches to the sum of the VIIRS satellites when S-NPP comes online (January 2012, the real switch). Aqua observed is the harmonized series through 2021.
- **MODIS 2000–2011 source:** the FIRMS yearly summaries by country, with a static-source mask built from our own 2012–2025 MODIS downloads. Without it, the newer static-source flag in those files would add 1–5% of industrial cell-days. On 2012, held out of the mask, the two sources agree to within ±0.6%. See DATA_CARD.

## 2. Sensor links (ADRs 0001, 0007)

Each link maps a source sensor onto a target's scale. It is fitted on region × week totals (10° regions), using only days when both sensors delivered full data.

- **Candidates:**
  - no correction;
  - one global ratio;
  - region (× month) ratios shrunk towards their parent (empirical Bayes; the strength is chosen by nested CV);
  - quantile mapping by region × season.
- **Validation:** leave one year out: NOAA-20 → S-NPP on 2018–2026 (9 folds), NOAA-21 → S-NPP on 2023–2026 (4), S-NPP → Aqua on 2013–2021 (9; Aqua's stable orbit, ADR 0001). With only one year, it falls back to leaving one month out.
- **Selection:** the **simplest** method within 2% of the best held-out region-month WAPE.
- **One year can't test month effects:** a held-out month has no month ratio, so month effects only ship once multi-year folds can validate them.
- **The 90% band:** held-out ratios observed/predicted, binned by magnitude, plus an additive upper bound when the prediction is 0. Its coverage is checked on folds it was not built from, and on whole-AOI weeks. A bootstrap over whole folds gives the confidence interval of the ratio.
- **Drift:** the report lists monthly held-out misses over 3% as caveats.

- **Drift check:** Aqua observed / predicted from S-NPP per year, globally (0.97–1.04 through 2025, 0.905 in 2026).

Results are in `reports/harmonization_report.json` and the README.

## 3. Calendar, climatology and anomalies (ADR 0006)

- **Usable weeks:** full weeks, or partial weeks with ≥ 5 data days (scaled to 7).
- **History:** a year counts as history if ≥ 75% of its weeks are usable. Climatology needs ≥ 5 history years; otherwise the panels say so.
- **Climatology per ISO week:** median, p10, p90 and the share of years active, pooled over ±1 week.
- **Activity gate** (rules fixed in advance):
  - default: ≥ 10% of years active;
  - relative: the top 20% of weeks, if fewer than 8 weeks pass;
  - floor: no critical periods if the mean is below 1 cell-day a week.
  - "Active" means ≥ 1 fire cell-day; a relative definition is a proposed amendment.
- **Anomalies:** each week is judged against a climatology built **without its own year**: ≥ p90 or z ≥ 2, inside the gate.
- **Critical periods:** runs of gated weeks, ranked by expected activity.
- **"This week vs history":** a percentile against the same week ±1 in the other history years.

## 4. Seven-day risk (ADRs 0004, 0005)

- **Label:** ≥ 1 NOAA-20 fire cell-day in the 0.25° cell in the next 7 days. One reference satellite keeps the base rate stable as satellites come and go.
- **Features:** NOAA-20 only; all from data up to the issue date.
- **Blocks:** weekly issue dates in three time-ordered blocks separated by the horizon:
  - train: to 2026-08-21;
  - validation: Aug 28 – Sep 25 (early stopping and calibration only);
  - test: Oct 2 – 30, scored once.
- **Training:** from scratch, with no refit on validation.
- **Calibration:** isotonic, fitted on validation.
- **Baselines:** persistence and the 2026 frequency, as probabilities.
- **Checks:** the new-activity subset, per-region results, and 5° spatial blocks with and without lat/lon.

Details: `docs/MODEL_CARD.md`.

## Reproduce

`python -m godseye clean data\raw` → `aggregate` → `harmonize` → `train-v2` → `evaluate`. Every number in the README and the model card comes from these commands.
