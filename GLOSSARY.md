# F.I.R.E.S.

Harmonized MODIS + VIIRS burning-activity records: a multi-year calendar per area, with a 7-day risk outlook on top.

## Observations

**Sensor**:
One instrument on one satellite: Terra-MODIS, Aqua-MODIS, S-NPP-VIIRS, NOAA-20-VIIRS, NOAA-21-VIIRS. Each is its own series.
_Avoid_: Satellite (when the instrument is meant), source

**Detection**:
One FIRMS active-fire record: one sensor reporting thermal anomaly in one pixel at one overpass.
_Avoid_: Fire, hotspot (in counts)

**Fire pixel**:
The ground footprint of a detection: ~1 km for MODIS, ~375 m for VIIRS, growing toward the scan edge.

**Fire cell-day**:
A ~1 km (0.01°) grid cell with at least one detection from a given sensor on a given day. The headline unit, because it is far less sensitive to pixel size than detections.
_Avoid_: Fire, fire day

**Coverage gap**:
A sensor-day when the sensor was not delivering full data: not operational (pre-launch or retired), no data (zero detections worldwide: an outage), or partial (far fewer detections worldwide than usual). Not-operational and no-data days are shown as "no data", never as zero activity. Partial days keep their count but are always flagged, never presented as complete. Cloud cover is a known, unmapped limitation, not a coverage gap.
_Avoid_: Zero, missing fire

**Kept detection**:
A detection that passed quality filtering (nominal or high confidence, vegetation fire, not a known static source). Every count we show, raw or harmonized, is of kept detections.
_Avoid_: Raw (when filtered data is meant)

## Harmonization

**Overlap period**:
Dates when two sensors both delivered data, so their series can be compared directly.

**Calibration window**:
The part of an overlap period used to fit the mapping between two sensors (for Aqua-MODIS vs S-NPP-VIIRS: the overlap years before Aqua's drift).

**Aqua-equivalent**:
A value expressed on the scale of Aqua-MODIS at its nominal ~13:30 afternoon overpass. The scale of the headline series across the whole record.
_Avoid_: MODIS-equivalent, combined MODIS, Terra+Aqua

**Harmonized value**:
An Aqua-equivalent estimate derived from another sensor's observations, always accompanied by its uncertainty band. Never presented as an observed count.
_Avoid_: Corrected fires, total fires

**Uncertainty band**:
The 90% interval around a harmonized value, from resampling the calibration years.

**Provisional calibration**:
A VIIRS → Aqua-equivalent mapping fitted on drifting-orbit years. Usable, but always labelled as provisional.

**Drifting orbit**:
Aqua-MODIS from 2022 onward, when its overpass time moved away from 13:30; still shown, but no longer the headline reference.

## Calendar

**AOI**:
Area of interest: a named region or a user-drawn bounding box over which a calendar is computed.
_Avoid_: Region (when an AOI is meant), zone

**Burning activity calendar**:
The year × week grid of Aqua-equivalent fire cell-days for one AOI, with per-sensor observed series alongside.

**Climatology**:
For one AOI and week of year, the distribution of past values: median, p10–p90, and the probability of any activity.
_Avoid_: Average, normal

**Anomaly**:
A week whose value is at or above the climatological p90 (or z ≥ 2), counted only in weeks that pass the activity gate.

**Activity gate**:
The rule deciding which weeks of an AOI are in season enough to count toward anomalies and critical periods.

**Critical period**:
A run of consecutive weeks where the climatological probability of activity is above a threshold; the AOI's fire season(s).
_Avoid_: Fire season (in code and UI)

## Risk outlook

**Issue date**:
The day a forecast is made; only data up to and including it may be used.

**Horizon**:
How far ahead a forecast speaks: 7 days.

**Reference satellite**:
The single sensor (NOAA-20-VIIRS) whose fire cell-days define risk labels and features, so the base rate doesn't change with the constellation.
_Avoid_: All VIIRS, any satellite

**Label window**:
Days t+1..t+7 after an issue date t, over which the outcome is observed.

**Persistence baseline**:
Forecast "activity next week if there was activity this past week".

**Climatology baseline**:
Forecast the cell's historical probability of activity for that time of year.

**New-activity subset**:
Cell-issue dates with no activity in the prior 30 days; where a forecast has to add value beyond persistence.
