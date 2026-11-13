# Claude Code mission prompt: God's Eye → competition-grade NASA Space Apps 2026 project

> Paste everything below this line into Claude Code, started from `C:\Users\muham\gods_eye`.
> Before pasting, fill in the two values in **§0**.

---

## §0 Fill these in first

- `DISPLAY_NAME` = `<<choose a new public name; "God's Eye View" is already the name of Bilawal Sidhu's viral open-source project we build on>>`
- `TEAM` = `<<team name, members (1–6), Local Event (for example NASA Space Apps Amman)>>`

If `DISPLAY_NAME` is still a placeholder when you reach Phase 1, ask me once, then continue. Keep the Python package name `godseye` (internal only). The display name lives in one config value.

---

## §1 Your role and mission

You are the lead engineer and scientific reviewer on a NASA Space Apps Challenge 2026 entry. The hackathon runs **Sat 14 Nov 09:00 → Sun 15 Nov 23:59 (Asia/Amman)**. Submission is final at the deadline.

We are entering the official challenge **"Harmonization of MODIS and VIIRS Hot Spots"** (Advanced/Intermediate, Earth Science + Software, authored by CONAE, Argentina). The core ask: *build a web application that harmonizes MODIS (1 km, since 2000) and VIIRS (375 m, since 2012) active-fire records into a burning activity calendar*, so fire managers, scientists and land managers can review historical burning patterns, unusual activity and critical periods for **an area they choose**.

Your job: turn the existing prototype into a clean, reproducible, honestly evaluated project that answers that challenge directly. Keep our 7-day risk model, 3D globe and AI agent as the differentiators built on top of it.

Judges score five equal criteria: **Influence, Creativity, Validity, Relevance, Presentation**. Every phase below has to make at least one of them measurably better. Our award targets are **Best Use of Science** and **Best Use of Data**, with **Local Impact** as a secondary.

---

## §2 What exists today (verified on disk; do not re-derive, but re-check before you change anything)

```
gods_eye/                      # NOT a git repo yet
├─ backend/main.py             # FastAPI: /api/health, /api/fires/recent(.geojson), /api/predictions/risk-map, /api/predictions/risk-at; serves frontend/
├─ scripts/clean_fire_data.py  # FIRMS CSV/zip → unified schema; filters; writes fires_clean / fires_daily_grid / fires_recent(.feather|.geojson)
├─ scripts/train_model.py      # Panel (cell×day) features, LightGBM native API, temporal holdout, baselines, pickle bundle
├─ models/gods_eye_risk_model.pkl + .json
├─ frontend/index.html         # Leaflet dashboard (fires / risk tabs)
├─ data/raw/DL_FIRE_*          # ~4.2 GB FIRMS archive+NRT CSVs (MODIS C6.1, VIIRS S-NPP, NOAA-20, NOAA-21)
├─ data/processed/             # ~1.2 GB feather + 137 MB geojson + risk_predictions.csv + cleaning_report.json
├─ logs/                       # pipeline + test logs
├─ requirements.txt            # pip freeze (Python 3.14)
└─ gods-eye-view/              # clone of github.com/bilawalsidhu/gods-eye-view (MIT © Bilawal Sidhu), upstream main @ c56d5f2
                               # our UNCOMMITTED changes: 27 modified + 7 new files (godsEye proxy, riskLayer, godsEyeRiskRaster, get_fire_risk tool, i18n, catalogs)
```

Facts from the logs:
- Cleaning: 51,019,714 input rows → 41,669,782 kept (VIIRS 38.97 M, MODIS 2.70 M). Dropped: 5.66 M below nominal confidence, 2.43 M non-vegetation type, 1.25 M NRT near known static sources, 13 k FRP ≤ 0.
- Coverage is **only 2026-01-01 → 2026-11-06**. S-NPP delivery ended 2 Nov 2026.
- Risk model: 125,854 cells × 310 days; train 3.10 M rows (33 weekly issue dates), validation 739,688 rows (6 issue dates, 2026-09-25 → 10-30). LightGBM ROC-AUC 0.884 / PR-AUC 0.797 / Brier 0.114, against persistence 0.769 / 0.535 / 0.190 and historical frequency 0.793 / 0.581 / 0.202. Top features: fire_days_14, fire_days_30, nbr_fire_days_7.
- gods-eye-view tests: one test fails before and after our change (`nominatimOutlineRoute.test.mjs`, a Windows file-permission assertion). It is not ours. Don't "fix" it by editing upstream tests.

**Machine constraints (Windows 11, Smart App Control ON):** the `scipy.stats` DLLs and the pyarrow `_parquet` DLL are blocked. Use feather/zstd, not parquet. Use the native LightGBM API, not the sklearn wrapper. Before you add **any** compiled dependency (geopandas, shapely, sklearn, scipy, numba…), run `python -c "import X"` and drop it if it fails. Prefer numpy/pandas implementations.

---

## §3 Gaps you must close (from the audit)

1. **No real cross-sensor harmonization.** Today MODIS and VIIRS share a schema, but VIIRS detections (≈ 14× more rows here) dominate every count, FRP sum and label. The challenge is about correcting exactly this.
2. **No history.** One year of data means no burning calendar, no climatology, no anomalies. The day-of-year features are also unreliable because validation months were never seen in training.
3. **The risk model mostly learns persistence.** Only cells that already burned in 2026 are scored, and the positive rate is about 30%. It has to be evaluated where it matters: cells with no recent fire (new activity), per region, and with calibration plots.
4. **Branding and attribution risk.** The project name equals the upstream project's name. The globe is a "spy-satellite simulator" with CCTV and aircraft layers that have nothing to do with fire. Our changes are uncommitted on someone else's main branch.
5. **Not a professional repo.** No git, no README, no tests for Python, no config, a pickle artifact, a `sys.path` hack, multi-GB data inside the project tree, and no model card or data card.

---

## §4 Non-negotiables (apply in every phase)

- **Never break the running demo.** Before each phase, confirm `backend` and `gods-eye-view` still start. Keep old entry points working (thin wrappers) until the new ones are tested.
- **Never add MODIS and VIIRS counts or FRP and call the result "fires".** Keep per-sensor series, and show harmonized values as model estimates with uncertainty.
- **Missing data ≠ zero fire.** Cloud, orbit gaps, sensor outages and the S-NPP end date must be explicit in the data and the UI.
- **Honest metrics only.** Every model number in the README or demo must be reproducible by one command and must be shown next to its baseline.
- **No leakage.** Time-based splits; label windows never overlap validation issue dates; spatial-block checks for the risk model.
- **Credit everything.** Keep upstream MIT notices. Add `docs/REFERENCES.md` listing every external dataset, library, code base and AI tool we used (Gemini, Claude, and Matt Pocock's agent skills, MIT). The submission's References field must list them all.
- **English** everywhere in the repo, the UI default and the submission. Arabic UI strings are a bonus, not a replacement.
- **No data or model binaries in git.** Use `.gitignore` plus a manifest with SHA-256 hashes and source URLs.
- **Small commits** with clear messages. Run the tests before every commit.
- **Ask before** deleting anything, force-pushing, or making a choice that cannot be undone.

---

## §4b Agent skills: Matt Pocock's skills (github.com/mattpocock/skills, MIT)

Use these skills as the engineering discipline for every phase. They help only if they stay inside the time caps, so every interview is time-boxed.

**Install (Phase 0, once).** Run `claude plugin install mattpocock-skills@claude-plugins-official`. If that marketplace isn't available, run `/plugin marketplace add mattpocock/skills` and then `/plugin install mattpocock-skills@mattpocock`. Restart Claude Code if the skills don't appear. Then run `/setup-matt-pocock-skills` and give it these answers:
- Issue tracker: **Local markdown** (`.scratch/<feature>/`). It's faster than GitHub Issues for a 48-hour solo or small team, and it works before the GitHub remote exists.
- Domain docs: **single-context**, meaning one `GLOSSARY.md` plus `docs/adr/` at the repo root.
- Agent-skills block: add it to our `CLAUDE.md`.

**Optional guardrail:** the `git-guardrails-claude-code` skill sits in the repo's `skills/misc/`, not in the plugin. It adds a hook that blocks `git push`, `reset --hard`, `clean -f` and `branch -D`. Install it **only if** its bash hook runs under this Windows setup (Git Bash). Test it once with a harmless blocked command. If the hook errors, remove it and carry on.

**Which skill in which phase:**

| When | Skill | Time-box | Output |
| --- | --- | --- | --- |
| Before Phase 1 | `/grill-with-docs` | 20 min | `GLOSSARY.md` (see the terms below) + ADRs |
| After grilling | `/to-spec` → `/to-tickets` | 15 min | Phases 3–6 as tracer-bullet tickets in `.scratch/`, with blocking edges |
| Each ticket | `/implement` (drives `/tdd` at agreed seams, ends with `/code-review`) | per phase cap | Tested, reviewed commit |
| Unknown API or method | `research` | 15 min, in the background | Cited markdown in `docs/research/` (FIRMS endpoints and limits, MODIS/VIIRS calibration literature) |
| Phase 6 UI choice | `prototype` | 30 min | 2–3 calendar layouts to pick from; then delete the losers |
| Anything broken or slow | `diagnosing-bugs` | until fixed | Regression test + fix |
| Editing CLAUDE.md or skills | `writing-for-agents` | — | Concise agent docs |
| Before sleep, or when context gets long | `/handoff` | 5 min | `docs/HANDOFF.md` so the next session resumes cleanly |
| A message doesn't land | `/wait-what` | — | Plain re-explanation |
| After the deadline | `/retro`, `/improve-codebase-architecture` | — | Post-event clean-up list |

**Seams for `/tdd`** (confirm these, don't add more during the hackathon):
1. `clean.harmonize_schema`: raw FIRMS rows in, unified rows out.
2. `harmonize`: per-sensor series + coefficients in, harmonized series + band out.
3. `calendar` API contract.
4. `risk.evaluate`: predictions + labels in, metrics out.

**GLOSSARY.md must define at least:** detection, fire pixel, fire cell-day, sensor, overlap period, calibration window, harmonized value, MODIS-equivalent, uncertainty band, AOI, coverage gap, burning activity calendar, climatology, anomaly, critical period, issue date, horizon, label window, persistence baseline, climatology baseline, new-activity subset.

**First ADRs:** 001 calibration method and window; 002 feather instead of parquet (Smart App Control); 003 own web app primary, globe secondary; 004 risk label definition; 005 validation design (train / validation / untouched test).

Don't use `/implement-spec` or `/wayfinder`. They fan out subagents and long planning loops that don't fit a 48-hour budget.

---

## §5 Target structure

```
gods_eye/
├─ README.md               # hero GIF, one-line pitch, challenge link, quickstart (≤5 commands), results table, limitations
├─ CLAUDE.md               # conventions + commands for future Claude Code sessions (write this in Phase 0)
├─ LICENSE                 # MIT (ours) — upstream notices preserved where code is reused
├─ CITATION.cff
├─ pyproject.toml          # package `godseye`, pinned direct deps only; requirements.lock kept separately
├─ configs/
│  ├─ pipeline.yaml        # grid_deg, min_confidence, date ranges, sensors, AOIs, paths
│  └─ aois.yaml            # named AOIs (bbox + label): jordan, levant, argentina, + any we add
├─ src/godseye/
│  ├─ config.py            # load yaml + env (GODSEYE_DATA_DIR, FIRMS_MAP_KEY) — one source of truth
│  ├─ ingest/              # firms_archive.py (local CSV/zip), firms_api.py (MAP_KEY, rate-limited), manifest.py
│  ├─ clean/               # current clean_fire_data logic, split into harmonize_schema / filters / io
│  ├─ harmonize/           # NEW — cross-sensor calibration (Phase 3)
│  ├─ calendar/            # NEW — AOI daily series, climatology, anomalies, critical periods (Phase 4)
│  ├─ risk/                # Panel features, train, evaluate, predict (Phase 5)
│  ├─ api/                 # FastAPI app factory, routers, pydantic response models, settings
│  └─ cli.py               # `python -m godseye <command>` (argparse, no extra deps)
├─ web/                    # our own focused app (Phase 6) — vendored JS libs, no CDN at demo time
├─ integrations/gods-eye-view/README.md   # how our fork/branch plugs in; link to the fork
├─ data/{raw,interim,processed}/  + data/README.md + data/manifest.json    # gitignored contents
├─ models/                 # gitignored binaries + models/registry.json (metadata only, committed)
├─ reports/figures/        # validation charts used in README/slides (committed, small PNG/SVG)
├─ notebooks/              # 01_eda, 02_harmonization_validation, 03_risk_evaluation (outputs cleared)
├─ tests/                  # pytest: schema, filters, harmonization math, calendar, API contract
├─ docs/                   # ARCHITECTURE.md (mermaid), DATA_CARD.md, METHODOLOGY.md, MODEL_CARD.md,
│                          # REFERENCES.md, AI_USAGE.md, DEMO_SCRIPT.md, SUBMISSION.md
└─ .github/workflows/ci.yml   # lint (ruff) + pytest on a tiny fixture dataset
```

---

## §6 Phases (in order; time budgets are hard caps)

Each phase starts with a short plan (≤10 bullets) and ends with a check report: what changed, the commands you ran, test results, and what is still open. Don't start the next phase until the current one's acceptance checks pass.

### Phase 0 — Safety net (≤45 min)
- `git init` at `gods_eye/`, with `.gitignore` covering `.venv`, `data/**` (keep the READMEs), `models/*.pkl|*.txt|*.bin`, `logs/`, `__pycache__`, `node_modules`, and `gods-eye-view/` (it becomes its own repo; see below). First commit = current code as-is, tagged `v0-prototype`.
- In `gods-eye-view/`: create branch `space-apps-2026` and commit our changes there, split into logical commits. Tell me the exact commands to fork on GitHub and push. I will run the push myself.
- Write `CLAUDE.md`: how to run backend, frontend, pipeline and tests; the Windows constraints from §2; the non-negotiables from §4.
- Install Matt Pocock's skills, run `/setup-matt-pocock-skills` (§4b), then `/grill-with-docs` (20 min) → `GLOSSARY.md` + ADRs 001–005 → `/to-spec` → `/to-tickets`.
- **Accept:** `git log` shows the tag; the backend still serves `/api/health`; `npm run dev` still starts the globe; `GLOSSARY.md`, `docs/adr/` and the `.scratch/` tickets exist.

### Phase 1 — Professional skeleton (≤2 h)
- Create the §5 layout. Move logic into `src/godseye/` with no behaviour change. Keep `scripts/*.py` as 3-line wrappers that call the CLI.
- Remove the `sys.path` hack (editable install: `pip install -e .`).
- `config.py` + `configs/pipeline.yaml` replace the hard-coded constants (grid, horizon, bins, paths).
- Replace the pickle artifact with LightGBM's native `model.txt` plus `model_meta.json` (features, params, data window, data hash, metrics, git SHA, created_at). Keep a loader that still reads the old pickle once, for migration.
- Pydantic response models for every endpoint. Add `/api/meta` (dataset coverage, sensors, model version, attribution).
- pytest with a tiny committed fixture (a few hundred FIRMS rows per sensor, including edge cases: zero-padded `acq_time`, VIIRS `l/n/h`, MODIS 0–100 confidence, type 1/2 rows, an antimeridian bbox).
- **Accept:** `pytest` is green; `python -m godseye api` serves the same JSON as before for the four endpoints (contract test compares old and new); `ruff` is clean.

### Phase 2 — History (start the downloads first; they run in the background)
- Goal: a multi-year record for the AOIs plus the overlap years needed for calibration.
  - MODIS C6.1 (Terra from Nov 2000, Aqua from Jul 2002) and VIIRS 375 m (S-NPP from 20 Jan 2012; NOAA-20 from 2020; NOAA-21 from 2024).
  - AOIs: `jordan`/`levant` (local impact), `argentina` (the challenge author's country), plus 2–3 contrasting fire regimes for calibration (for example a savanna, a boreal and a cropland-burning region). Keep the existing 2026 global files for the globe.
- Sources, in order of preference (check each endpoint in the FIRMS docs before coding it, don't guess parameters): FIRMS archive download requests (the `DL_FIRE_*` zips we already use), FIRMS yearly country files, and the FIRMS area API with `FIRMS_MAP_KEY` (respect its rate and day-range limits; cache every response).
- Stream the data into **per-sensor** daily aggregates on two grids: 0.25° (for the model and the globe) and about 1 km (0.01°, to count fire cells independently of pixel size). Also write `data/manifest.json` (file, source URL, date range, rows, sha256).
- **Accept:** `python -m godseye ingest --aoi jordan` is idempotent; the manifest is written; a coverage chart (sensor × year) is saved to `reports/figures/`.

### Phase 3 — Cross-sensor harmonization: THE CORE (≤6 h)
Build `godseye.harmonize` and `notebooks/02_harmonization_validation`.
- **Unit:** AOI (or region block) × day / week / month, kept per sensor.
- **Metrics per sensor:** detections; *fire cell-days* (unique ≈1 km cells with ≥1 detection; less sensitive to the 375 m vs 1 km pixel size); FRP sum. Never sum sensors.
- **Pairing:** calibrate on **Aqua-MODIS vs S-NPP-VIIRS** (same ~13:30 afternoon orbit) during the overlap. Prefer **2013–2021** as the calibration window, before Aqua's orbit drift. Treat Terra (morning orbit) separately. Treat NOAA-20/21 as VIIRS continuity once checked against S-NPP in their own overlap.
- **Candidates (compare all, pick by out-of-sample error):**
  1. a global ratio;
  2. a region × month ratio with shrinkage to the global prior (empirical-Bayes style);
  3. quantile mapping per region × season.
- **Validation:** leave-one-year-out across the overlap; report MAE / MAPE and correlation of monthly series; a 90% uncertainty band from bootstrapping over years; a drift check on 2022–2026.
- **Headline figure:** raw MODIS+VIIRS series showing the artificial jump at 2012, next to the harmonized series with its uncertainty band, for Jordan/Levant and for Argentina. This figure goes in the README, the slides and the video.
- Output: `harmonization_coefficients.feather` + `harmonization_report.json` (method chosen, CV scores, caveats).
- **Accept:** unit tests for the math; the notebook runs top to bottom; the report shows the chosen method beating the global-ratio baseline out of sample (if it does not, say so, and ship the simpler method).

### Phase 4 — Burning activity calendar API (≤4 h)
Endpoints (pydantic models; bbox or named AOI):
- `GET /api/calendar?aoi=|bbox=&unit=day|week&metric=cell_days|detections` → year × period grid, per-sensor raw, harmonized value + band, and a `coverage` flag.
- `GET /api/calendar/climatology` → per week-of-year median, p10/p90, and the probability of any activity.
- `GET /api/calendar/anomalies` → periods ≥ p90 or with z ≥ 2, excluding off-season noise.
- `GET /api/calendar/critical-periods` → contiguous weeks where the climatological probability of activity is above a threshold, ranked.
- `GET /api/calendar/now` → this week vs the same weeks in every past year (percentile + plain-language status).
- **Accept:** API contract tests; response time under 1 s for a country-size AOI (pre-aggregate; no scanning of raw rows per request).

### Phase 5 — Risk model v2 and model card (≤4 h)
- Retrain on the harmonized daily grid. Label: *any harmonized activity in the cell in days t+1..t+7*. Training window: the multi-year AOIs plus 2026 global. Keep the issue-date step and the no-overlap rule.
- **Fix the v1 validation leak.** In v1, early stopping picked the number of trees on the same 6 weeks that the metrics were reported on, so 0.884 is slightly optimistic. Also, the shipped model was refit on train + validation and never scored. v2 uses three time-ordered blocks, each separated by the 7-day horizon gap: **train**, **validation** (early stopping, calibration, thresholds), and an **untouched test** block (the last 4–6 issue dates, scored once at the end). Every number in the README and the demo comes from the test block. Record the split dates in ADR 005.
- **Train v2 from scratch; don't warm-start from v1** (`init_model=` or `refit`). v1 was refit on all 2026 labels, including the new test block, so continuing from it leaks the test set. v2 also changes the label, the features and the input scale (harmonized counts), so v1's trees would encode the wrong target. A full training run took about 22 s in v1. Keep v1 only as a comparison row in the model card. Optional, only if time remains after Phase 7: show warm-start as an *operations* feature (daily NRT update with `init_model`), validated against a full retrain on the same test block.
- Features: keep the current 22; add climatological fire probability for the issue week (from Phase 4), years since last activity, and sensor-coverage flags. Drop raw lat/lon if spatial-block checks show it memorizing places.
- **Evaluation suite** (`python -m godseye evaluate`, all results to `reports/`):
  - ROC-AUC, PR-AUC, Brier, and **Brier Skill Score vs persistence and vs climatology**;
  - a reliability diagram plus a calibration step (Platt or isotonic, written in numpy);
  - the **new-activity subset** (no fire in the cell in the prior 30 days), reported separately;
  - per-region metrics; spatial-block cross-validation (e.g. 5° blocks);
  - risk-level thresholds justified by observed rates, not picked by hand;
  - global importance (gain) plus per-prediction contributions via LightGBM `pred_contrib=True` (no shap dependency).
- Never call ROC-AUC "accuracy" anywhere: not in the README, the UI, the slides or the video. State the metric's name, the test window and the baseline beside it.
- `docs/MODEL_CARD.md`: intended use (*planning aid for regional burning activity, not ignition prediction*), data, splits, metrics with baselines, the new-activity results, calibration, failure modes (persistence dominance, cropland burning counted as "fire", cells never burned are not scored, clouds), and ethical notes.
- **Accept:** one command reproduces every number in the model card; the old metrics are kept in the card for comparison.

### Phase 6 — Product surface (≤6 h)
- **`web/` (primary, our own UI).** Map with AOI select (named AOIs + draw a bbox) → calendar heatmap (year rows × day/week columns; raw/harmonized toggle) → seasonal profile with the p10–p90 band → anomaly list → critical periods → "This week vs history" card → "Next 7 days" risk panel. The coverage and limitations notes are always visible. Data source credits sit in the footer. Vendor all JS libs locally so the demo works offline.
- **gods-eye-view fork (secondary "wow" mode, on branch `space-apps-2026`):** keep our Active Fires + 7-day Risk layers. Add a `get_burning_calendar` agent tool beside `get_fire_risk`, so the assistant can answer things like *"Is this week unusual for northern Jordan?"* from our API. Add a fire-focused startup preset that turns off the unrelated layers (CCTV, aircraft, ships, traffic) for the demo. Credit the upstream project visibly in the UI and the README. Don't change upstream licensing text.
- **Accept:** cold start to first calendar in under 10 s on this laptop; no console errors; screenshots and a GIF saved to `reports/figures/`.

### Phase 7 — Quality gate (≤2 h)
- README (≤2 screens above the fold), ARCHITECTURE.md with a mermaid diagram (ingest → clean → harmonize → calendar/risk → API → web/globe), DATA_CARD.md (sources, licences, citations as FIRMS asks, known gaps such as the S-NPP end of 2 Nov 2026 and MODIS retirement), METHODOLOGY.md, REFERENCES.md, AI_USAGE.md.
- CI green on the fixture. `ruff` clean. No secrets in the repo (scan for MAP_KEY and API keys).
- **Accept:** a fresh clone + the README quickstart reaches a working calendar using the fixture/sample data in under 5 commands.

### Phase 8 — Submission kit (≤2 h; finish by Sun 15 Nov 20:00 Amman time)
Write `docs/SUBMISSION.md` with drafts for every field on the project page:
- High-level summary (≤150 words).
- Project details: what it does, how it works, benefits, intended impact, tools and languages.
- How NASA data was used: product names (MCD14ML / VNP14IMG / VJ114IMG / VJ214IMG via FIRMS) with versions and dates.
- Space Agency partner data, if any.
- References: everything from REFERENCES.md, including gods-eye-view and the AI tools.

Also produce:
- **Demo (pick one; the limits are strict):** a ≤30-second video script (shot list + English captions) **or** a ≤7-slide outline (title slide included).
- `docs/DEMO_SCRIPT.md`: a 3-minute live-pitch version for local judging.
- A final checklist: team members registered and on the Members tab; public repo link; public demo link; English; References complete; the challenge selected = "Harmonization of MODIS and VIIRS Hot Spots".

---

## §7 How to work with me

- Start by reading this whole prompt and the files in §2. Then reply with (a) anything in §2 that doesn't match reality and (b) your Phase 0 plan. Wait for my "go".
- After that, run phases back-to-back. Stop and ask only for: anything irreversible, a credential (FIRMS MAP_KEY, GitHub push), or a choice between two scientifically defensible methods where the cost of choosing wrong is high.
- If a phase is going over its time cap, cut scope (fewer AOIs, a simpler harmonization method, fewer UI panels) rather than quality. Tell me what you cut.
- Keep a running `docs/CHANGELOG_HACKATHON.md`: a timestamp, what was done, and what's next. It is our evidence of what was built during the event.
- Work ticket by ticket from `.scratch/` with `/implement`. Run `/handoff` before each long break and before the context gets full, so the next session starts from `docs/HANDOFF.md` instead of re-reading everything.

## §8 Definition of done

- [ ] Challenge question answered: pick an AOI → see a harmonized multi-year burning calendar, anomalies, critical periods and "this week vs history".
- [ ] Harmonization validated out of sample, with an uncertainty band; the "2012 jump removed" figure exists.
- [ ] Risk model v2 scored once on an untouched test block, with skill vs persistence and climatology, new-activity results, calibration, and a model card.
- [ ] `GLOSSARY.md`, ADRs 001–005, and `.scratch/` tickets all closed or explicitly cut.
- [ ] Reproducible: `pip install -e .` → `python -m godseye ingest|clean|harmonize|calendar|train|evaluate|api`.
- [ ] Tests + CI green; no data, keys or binaries in git; MIT + upstream notices + REFERENCES + AI_USAGE.
- [ ] Our own web app works offline; the globe fork works with its fire preset and both agent tools.
- [ ] SUBMISSION.md, a demo within limits, and the README with figures, all in English.
