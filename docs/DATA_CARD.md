# Data card

## Source

**NASA FIRMS active fire detections** (Fire Information for Resource Management System, LANCE / ESDIS), downloaded with the FIRMS archive download tool. Every file, request id, date range, row count and sha256 is in `data/manifest.json`.

| Sensor | Product (via FIRMS) | Pixel | Overpass (local solar time, daytime) | In our data |
|---|---|---|---|---|
| Terra-MODIS | MCD14ML, Collection 6.1 | ~1 km | ~09:10 in 2026 (morning orbit, drifting) | 2012-01-01 → 2026-11-06 |
| Aqua-MODIS | MCD14ML, Collection 6.1 | ~1 km | ~15:24 in 2026 (drifted from 13:30) | 2012-01-01 → 2026-11-06 |
| S-NPP-VIIRS | VNP14IMG, Collection 2 | 375 m | ~13:34 | 2012-01-20 → **2026-11-02 (end of mission)** |
| NOAA-20-VIIRS | VJ114IMG, Collection 2 | 375 m | ~13:30 | 2018-04-01 → 2026-11-06 |
| NOAA-21-VIIRS | VJ214IMG, Collection 2 | 375 m | ~13:26 | 2023-03-01 → 2026-11-06 |

The overpass times are measured from our own data: the median of `acq_time` + longitude/15 over daytime detections.

- **Volume:** 2012–2025: 39 yearly global archive (standard) files, 558,898,261 records, read in place from the zips (never extracted). 2026: 51,019,714 records, archive up to Jul 31 (VIIRS) or Aug 31 (MODIS), then near-real-time (NRT). The archive ends 2025-12-31 and the 2026 files start 2026-01-01; the ingest asserts that they never overlap.
- **Licence:** NASA data, no restrictions. Required acknowledgement: "We acknowledge the use of data and/or imagery from NASA's Fire Information for Resource Management System (FIRMS) (https://www.earthdata.nasa.gov/firms), part of NASA's Earth Science Data and Information System (ESDIS)."
- **Citations:** Giglio et al. (2016), *Remote Sensing of Environment* 178, 31–41 (MODIS C6). Schroeder et al. (2014), *Remote Sensing of Environment* 143, 85–96 (VIIRS 375 m).

## Processing

- **Kept detections:** nominal or high confidence (MODIS ≥ 30; VIIRS n/h), FRP > 0, vegetation fires (archive `type` 0), and NRT detections not on known static sources (volcanoes, industry). 41,669,782 kept (82%). The report is in `data/processed/cleaning_report.json`.
- **Fire cell-day:** a 0.01° cell with ≥ 1 kept detection from one sensor on one day. Counted per sensor, never summed across sensors.
- **Availability (coverage gaps):** per sensor and day it is `ok`, `partial`, `no_data` (zero detections worldwide: an outage) or `not_operational`.
  - "Partial" means far below the sensor's usual global count, or (VIIRS only) far below the other VIIRS satellites that day.
  - Gaps are shown as "no data", never zero.

## Known gaps and issues

- **S-NPP** ended on 2026-11-02. It also had 14 full outage days (Mar 10–12, Apr 28–30, Jun 1–2, Jul 11–16) and 10 partial-delivery days (down to 39% of NOAA-20 on Oct 13). In October, its last full month, it read about 2–4% low against both NOAA satellites.
- **Aqua's orbit has drifted** to a later afternoon overpass, and Terra's to an earlier morning one. The MODIS missions are near the end of their lives.
- **Clouds** hide fires and are not mapped. Thick smoke and dense canopy also hide some fires.
- **NRT and archive differ slightly**, and NRT is replaced by standard data later.
- **No data before 2012:** no Terra-only years (2000–2002) and no MODIS-only era in our record.
- **Outages 2012–2025** (no data / partial days): Terra 21 / 4, Aqua 16 / 8, S-NPP 35 / 47, NOAA-20 6 / 36, NOAA-21 2 / 12.
