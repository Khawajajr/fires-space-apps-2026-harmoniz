# Risk label and VIIRS features use NOAA-20 alone

Label: a 0.25° cell is positive at issue date t if it has ≥1 **NOAA-20-VIIRS** fire cell-day in t+1..t+7. Every VIIRS-based feature is also computed from NOAA-20 only. Training data: 2026 global, plus NOAA-20 2020–2025 for the AOIs once those archives exist.

NOAA-20 has been operational since 2020 and is still running, so it covers the whole 2026 window through 2026-11-06. That keeps the ADR 0005 blocks valid and lets the model run in live operations.

## Considered options

- **"Any harmonized activity"** (the brief's wording): rejected because harmonization coefficients calibrate aggregate counts over AOIs and regions. They can't turn one cell's yes/no into a calibrated yes/no.
- **Union of VIIRS satellites:** rejected because sensitivity rises with every satellite added (1 satellite 2012–19, 2 from 2020, 3 from 2024, 2 again after S-NPP ended on 2 Nov 2026). The base rate would then drift with the constellation, not with fire.
- **S-NPP as the reference:** rejected because it ended on 2 Nov 2026, so it can't label the test block's last week or score live forecasts.
