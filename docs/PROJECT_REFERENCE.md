# SpectraFuse project reference

SpectraFuse compares satellite hotspot activity across NASA FIRMS products. The dashboard harmonizes monthly detection counts to the VIIRS Suomi-NPP scale. Separate research scripts model fire radiative power (FRP), in megawatts, using matched Aqua MODIS and NOAA-20 VIIRS detections.

## Start here

- [How to run](../HOW_TO_RUN.md) covers Windows setup, local launch, and Vercel deployment.
- [README](../README.md) covers downloads, region selection, Docker, and demo recording.
- [Submission guide](../SUBMISSION.md) covers the presentation and demonstration sequence.
- [Sri Lanka pilot notebook](../notebooks/sri-lanka-pilot.ipynb) walks through overlap, holdout, anomalies, and spatial validation.

## Dataset inventory

| Location under `data/` | Contents and role |
| --- | --- |
| `d73f2ecaea43efef/` | Sri Lanka dashboard archive for bounds `79.5,5.8,82,10` |
| `ed6d413b174027ef/` | Central Thailand dashboard archive for bounds `101,14,102,15` |
| `demo/` | Synthetic observations for local demonstrations |
| `sri-lanka-2000-2025/` | Long-history Sri Lanka research inputs, including combined MODIS, S-NPP, and NOAA-20 CSVs, monthly calendar exports, and daily plotting inputs under `modis/` and `viirs-jpss1/` |
| `frp-plots/` | Matched pairs, model coefficients, monthly matched-pair summaries, and synthetic historical estimates |
| `demo-recording/` | Local demo recordings, when generated |

The three standard-processing product codes are `MODIS_SP`, `VIIRS_SNPP_SP`, and `VIIRS_NOAA20_SP`. NOAA-20 is also known as JPSS-1. MODIS inputs can contain Terra and Aqua. An archive folder name describes intended scope. Use the daily partitions and product dates to establish actual coverage.

Each dashboard archive has an `area.txt` marker and stores UTC daily CSVs in `raw/<product>/` and normalized Parquet in `processed/<product>/`. Regional monthly exports are in `harmonized/monthly.csv` and `harmonized/monthly.parquet`. The download step validates coordinates, timestamps, confidence, day/night flags, and FRP. It deduplicates records by sensor, platform, location, and acquisition time. Re-running sync resumes from validated files. A header-only input can represent a successful day with zero detections.

## Monthly detection-count calibration

1. Sum each sensor's detections for months with all UTC daily partitions present. A complete month may have a zero total. Missing partitions leave the sensor total unavailable.
2. Sort months where both MODIS and S-NPP are available. Hold out the most recent quarter, with at least one month. Fit on the earlier paired months using total S-NPP detections divided by total MODIS detections. The fit needs at least three training months and positive totals.
3. Compare raw and scaled MODIS against S-NPP on the holdout. Use observed S-NPP when present, and use scaled MODIS when S-NPP is unavailable and the model and MODIS total are available. The monthly export retains the origin of each value.
4. Calculate seasonal departures against the median of at least two earlier values from the same calendar month. The dashboard estimate range uses the holdout's 90th percentile absolute error, with a lower bound clipped at zero.

NOAA-20 appears as a separate comparison series. The map groups raw detections at recorded coordinates and shows harmonized activity on an approximately 5 km angular grid. The box and optional polygon limit the selected area. Map coverage describes downloaded days, and a complete archive can still contain satellite coverage gaps.

### Recorded Sri Lanka pilot results

| Evaluation | Raw MODIS MAE | Calibrated MODIS MAE |
| --- | ---: | ---: |
| Regional monthly holdout, detections per month | 456.44 | 138.35 |
| Spatial diagnostic across 7,052 occupied grid-days, detections per grid-day | 1.38 | 2.38 |

These values come from the saved [monthly holdout](../data/d73f2ecaea43efef/harmonized/pilot/holdout-metrics.csv) and [spatial diagnostic](../data/d73f2ecaea43efef/harmonized/pilot/spatial-validation.csv). The monthly fit reduced regional error while increasing spatial error. The empirical range has no guaranteed coverage for individual grid cells, custom date ranges, or other regions. Hotspot counts represent detected thermal observations and may include repeated observations or non-fire thermal sources. Burned area and unique fire-event counts require additional evidence.

## Fire radiative power research

Run these commands from the repository root after local setup. They regenerate their corresponding outputs.

```powershell
.\.venv\Scripts\python.exe scripts/match_frp_archives.py
.\.venv\Scripts\python.exe scripts/train_viirs_frp.py
.\.venv\Scripts\python.exe scripts/harmonize_frp.py
.\.venv\Scripts\python.exe scripts/backcast_viirs_frp.py
```

| Step | Inputs and method | Output |
| --- | --- | --- |
| Match | Combined Sri Lanka MODIS and NOAA-20 CSVs. Keep Aqua pairs within 0.5 km and 10 minutes, using great-circle distance and absolute time difference. A detection can appear in multiple pairs. | `frp-plots/modis-noaa20-matches.csv` with source record numbers, offsets, and both original readings. Without `--merged-only`, also writes the distinct source records to `processed data/`. |
| Train | Fit ordinary least squares on finite pairs using MODIS FRP, distance, and time difference. Set the cutoff at the 80% position of sorted unique acquisition dates. Train with both dates before the cutoff and test with both dates on or after it. | `frp-plots/viirs-frp-model.json` with intercept, coefficients, minimum prediction, and cutoff date. The command prints test MAE, training-mean baseline MAE, and R² when test variance permits. |
| Summarize | Predict NOAA-20 FRP for matched pairs, clip at zero, and group by VIIRS acquisition month and split. | `frp-plots/monthly-frp-harmonization.csv` with pair counts and Aqua, observed NOAA-20, and estimated NOAA-20 FRP sums. Multiple matches can count a source detection more than once. |
| Backcast | Apply the Aqua-trained model to MODIS rows from 2000 through 2018 with valid FRP. Evaluate at zero spatial and time offsets and flag Terra transfers. | `frp-plots/sri-lanka-synthetic-noaa20-2000-2018.csv` with source platform, source and estimated FRP, and synthetic provenance. |

The matched-pair summaries cover the paired sample. The backcast estimates what the model would predict for a MODIS detection and retains that detection's date and coordinates. Its zero-offset assumption and transfer from Aqua to Terra require separate validation. Neither output contributes to the dashboard's monthly detection-count calibration.

The optional `scripts/plot_frp.py` reads the daily archive folders and uses its own date and matching settings. `scripts/correlate_frp_archives.py` calculates Pearson correlation from the merged pair export and opens a temporary plot. Its current plot label says NOAA-21, while the matcher reads the NOAA-20 archive. Use the source CSV to identify the platform.

The FRP steps above describe the current workspace. The Aqua-only matcher and revised summary have local edits, and the backcast script is currently untracked. Keep these scripts together when reproducing the workflow.

## Application and API

React and Leaflet provide the main dashboard. FastAPI serves the prepared data and the built frontend. The Streamlit application is a separate local interface. API paths below share the prefix `/api/fire`. Open `/docs` on the running server for request schemas and interactive calls.

| Method and path | Purpose |
| --- | --- |
| `GET /regions` | List downloaded dashboard regions from archive markers |
| `GET /dashboard` | Load calendar rows, NOAA-20 comparison, anomaly columns, and estimate bounds when available |
| `GET /calendar` | Read monthly counts and provenance, with an optional year |
| `GET /historical-trends` | Read the full monthly calendar series |
| `GET /anomalies` | Read seasonal departures for the harmonized series |
| `GET /sensor-comparison` | Read paired holdout months and comparison metrics |
| `GET /hotspots` | Read a UTC day and product with pagination |
| `GET /monthly-hotspots` | Read monthly map cells or detection CSV for a product, optionally filtered by polygon |
| `GET /map-layers` | Read raw and harmonized layers for an inclusive UTC range of up to 31 days, with spatial filters |
| `POST /area-analysis` | Recalculate monthly activity within a bounding box in the downloaded extent |
| `GET /download` | Export dashboard calendar rows as CSV, optionally filtered by year |

Use `region=sri-lanka` for the pilot or the region ID returned by `/regions`. The local synthetic archive also accepts `region=demo`. The server locates data through `FIRESCOPE_DATA_DIR` or defaults to the project data folder. The FIRMS key belongs in the local sync environment. The browser and read-only deployment use prepared files.

## AI assistant and chat API

The assistant answers from the same Parquet archive as the dashboard. A deterministic router and guardrail run first. Greetings, thanks, help, farewells and acknowledgments get fixed replies with no data query and no model call. Injection, jailbreak, credential and SQL-style probes are refused before any tool runs. Everything else goes to the orchestrator, which delegates to one specialist agent. The validation agent then checks the draft against the evidence, scans for secrets and file paths, and appends the standing limitation.

| Agent | Responsibility |
| --- | --- |
| Orchestrator | Classifies intent, extracts region, year, month, dates and bounding box, and delegates. |
| Data query | Monthly counts with observed, estimated or unavailable provenance, and ranked peak months. |
| Analysis | Sensor comparison over matched months, seasonal departure, calibration factor and holdout error. |
| Map | Validates dates (1 to 31 inclusive UTC days) and bounds, then emits a `show_on_map` action. |
| Explanation | Methodology answers drawn from a fixed knowledge base built from the project documents. |
| Export | Builds a download URL for the exact slice the user asked about. |
| Validation | Verifies numerical grounding, estimated versus observed wording, and secret leakage. |

All paths below share the prefix `/api/fire`.

| Method and path | Purpose |
| --- | --- |
| `POST /chat` | Ask a question. Body fields: `message` (up to 4,000 characters), optional `session_id`, `region`, `context` and `history`. |
| `GET /chat/health` | Active provider, fallback status, live session count and memory window. |
| `GET /chat/capabilities` | Supported intents, deterministic tools and memory settings. |
| `DELETE /chat/session/{session_id}` | Delete one session's memory. |

A chat response contains `request_id`, `session_id`, `intent`, `answer`, `region`, `period`, `evidence`, `calculations`, `limitations`, `ui_actions` and `downloads`. Each evidence item records its source, sensor product, metric, exact value, status, coverage and whether the regional multiplier was applied. Calculation steps give the formula and result. A `show_on_map` action carries the region, UTC date range and optional bounding box that the dashboard applies to the Leaflet map.

### Session memory

Each session keeps the last four question and answer pairs (eight turns), the active region, year, month and period, and the last detections. A follow-up such as *"explain that"* or *"show it on the map"* resolves against this window. Conversational pleasantries are recorded but never overwrite the scientific context, so *"thank you"* followed by *"show that on the map"* still targets the earlier data. Sessions expire after 7,200 seconds of inactivity and the store holds at most 5,000 sessions, evicting the least recently used. The store is in process memory. Run a single worker, or move the store to shared storage, before scaling out. See the hosting guide for the options.

### Providers

`LLM_PROVIDER` selects `groq`, `gemini` or `openai`, each with its own `*_API_KEY` and `*_MODEL`. Calls use HTTPS with a 15 second timeout and two retries on 429 and 5xx responses. A failure after the retries falls back to the offline provider. `USE_MOCK_MODEL=true` forces offline mode. The health endpoint reports the active provider as, for example, `gemini (fallback: mock)`.

### Evaluation

`backend/tests/evaluation_dataset.json` holds 22 benchmark questions, EV-01 to EV-22. `backend/tests/test_evaluation_runner.py` checks the classified intent, required text, forbidden text, evidence count and status, calculation steps, UI actions, downloads and the mandatory limitation for each one. The set covers monthly summaries, sensor comparison, peak months, seasonal anomalies, map requests, provenance, calibration, export, methodology, out-of-archive months, date and bounds validation, greetings, and refusal of prompt injection, credential probes and SQL injection.

## Maintenance and verification

| Task | Entry point or check |
| --- | --- |
| Run every backend test, including the evaluation benchmark | `python -m pytest backend/tests -q` |
| Type-check the backend | `pyrefly check backend --min-severity=warn` |
| Check the chat panel in a browser | `npx playwright test tests/chat.spec.js` from `frontend`, with `FIRESCOPE_TEST_URL` set to the running app |
| Check chat health after a deployment | `GET /api/fire/chat/health` should report `healthy` and the expected provider |
| Resume historical downloads | `backend/scripts/history.ps1`. Check completed date partitions and rerun sync after quota recovery. |
| Generate the pilot report | `backend/scripts/pilot_report.py`. Use `--partial` for a separate interim report while syncing. |
| Compare NOAA-20 against the Sri Lanka holdout | `backend/scripts/noaa20_validation.py` |
| Check processing and analytics | `.\.venv\Scripts\python.exe -m pytest -q` |
| Build React | `npm.cmd --prefix frontend run build` |
| Check the dashboard | Run the local app, open Sri Lanka, switch product and year, select a month, check layer coverage, and download both CSV types. Use the dashboard smoke check and Playwright instructions in the run guides. |
| Check a deployment preview | Confirm the dashboard, `/api/fire/regions`, and the Sri Lanka map all load on the preview domain. Re-stage after changing the prepared data. |

If a dataset returns 404, check the region marker, data directory, and requested daily partition. If a monthly count is blank, check whether every day in that product's month is present. If the basemap is blank while overlays load, check the browser's internet connection.
