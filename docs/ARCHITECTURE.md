# Architecture

```mermaid
flowchart LR
  subgraph Ingest
    RAW[FIRMS CSV/zip<br/>MODIS C6.1, VIIRS 375 m] --> CLEAN[clean<br/>unified schema, filters]
    CLEAN --> AGG[aggregate<br/>per-sensor fire cells 0.01°,<br/>sensor grid 0.25°, availability]
    RAW --> MAN[manifest<br/>sha256, dates, rows]
  end
  subgraph Science
    AGG --> HARM[harmonize<br/>sensor links, CV, bands]
    AGG --> RISK[train-v2 / evaluate<br/>NOAA-20 risk model, model card]
  end
  subgraph Serve
    AGG --> STORE[CalendarStore<br/>in memory]
    HARM --> STORE
    STORE --> API[FastAPI<br/>/api/calendar, climatology,<br/>anomalies, critical-periods, now, meta]
    RISK --> API2[/api/predictions/*]
  end
  API --> WEB[web/ calendar app<br/>offline, Leaflet]
  API2 --> WEB
  API --> GLOBE[gods-eye-view fork<br/>proxy + agent tools]
  API2 --> GLOBE
```

| Package | Responsibility | Seam (tested) |
|---|---|---|
| `godseye.clean` | FIRMS rows → unified schema; quality filters | `harmonize_schema` (seam 1) |
| `godseye.ingest` | per-sensor aggregates, availability (coverage gaps), manifest, coverage chart | |
| `godseye.harmonize` | paired series, candidate links, leave-one-out CV, bands, report, figures | `harmonize` (seam 2) |
| `godseye.calendar` | store, year × period folding, harmonized headline, climatology / gate / anomalies | calendar API (seam 3) |
| `godseye.risk` | v1 panel, v2 panel + blocks, training, evaluation suite, calibration, artifacts | `risk.evaluate` (seam 4) |
| `godseye.api` | FastAPI app, routers, pydantic models | contract tests |
| `web/` | plain JS app, vendored Leaflet, Natural Earth basemap | browser checks |

Data and model binaries never go in git. `data/manifest.json` and `models/*/model_meta.json` record what was used. Configuration lives in `configs/pipeline.yaml` and `configs/aois.yaml`. Decisions are in `docs/adr/`.
