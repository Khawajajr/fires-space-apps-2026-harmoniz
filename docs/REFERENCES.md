# References

Everything this project uses that we did not write. The submission's References field copies this list.

## Data

- **NASA FIRMS active fire data** (Fire Information for Resource Management System), LANCE / NASA ESDIS.
  https://firms.modaps.eosdis.nasa.gov/ . Downloaded through the FIRMS archive download tool; see `data/manifest.json` for every file, request id, date range and sha256.
  - MODIS Collection 6.1 active fire (Terra and Aqua, MCD14ML via FIRMS). Giglio, L., Schroeder, W., Justice, C. O. (2016). The collection 6 MODIS active fire detection algorithm and fire products. *Remote Sensing of Environment*, 178, 31–41.
  - VIIRS 375 m active fire, Collection 2 (S-NPP VNP14IMG, NOAA-20 VJ114IMG, NOAA-21 VJ214IMG via FIRMS). Schroeder, W., Oliva, P., Giglio, L., Csiszar, I. A. (2014). The New VIIRS 375 m active fire detection data product. *Remote Sensing of Environment*, 143, 85–96.
  - FIRMS acknowledgement: "We acknowledge the use of data and/or imagery from NASA's Fire Information for Resource Management System (FIRMS) (https://www.earthdata.nasa.gov/firms), part of NASA's Earth Science Data and Information System (ESDIS)."

- **Natural Earth** admin-0 countries (public domain), for the offline basemap of the calendar app: https://www.naturalearthdata.com/ . "Made with Natural Earth."

## Code we build on

- **gods-eye-view** by Bilawal Sidhu, MIT licence. https://github.com/bilawalsidhu/gods-eye-view . Our fork adds fire layers and agent tools on branch `space-apps-2026`. Upstream notices are kept.

## Libraries

- Python: FastAPI, Uvicorn, Pydantic, pandas, NumPy, PyArrow (feather), LightGBM, PyYAML, Matplotlib; pytest, Ruff and httpx for development. Exact versions are in `requirements.lock`.
- JavaScript: Leaflet 1.9.4 (BSD-2-Clause), vendored in `web/vendor/leaflet/` with its licence. Globe fork: see `gods-eye-view/package.json`.

## AI tools

- **Claude** (Anthropic), through Claude Code: pair-programming, code review and documentation. See `docs/AI_USAGE.md`.
- **Gemini** (Google): used in the prototype phase.
- **Matt Pocock's agent skills**, MIT licence. https://github.com/mattpocock/skills . Used for the engineering workflow (grilling, glossary/ADRs, spec, tickets, TDD, code review).
