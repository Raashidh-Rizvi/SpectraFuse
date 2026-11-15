# How to run SpectraFuse

Run these commands in PowerShell from the repository root. Install Python 3.13 and Node.js 22 with npm first.

## Run the dashboard locally

```powershell
powershell -ExecutionPolicy Bypass -File .\backend\scripts\setup.ps1
powershell -ExecutionPolicy Bypass -File .\backend\scripts\run-web.ps1 -Port 8002
```

Open [the dashboard](http://127.0.0.1:8002/) or [the FastAPI docs](http://127.0.0.1:8002/docs). The launcher builds React and serves both the dashboard and API from the same address. If port 8002 is occupied, choose another port and use it in the URL. Press Ctrl+C to stop the server.

Keep the repository dataset in `data/`. The prepared data works without a NASA FIRMS key. The key is needed when downloading new observations. See [README.md](README.md) for the sync commands.

## Run the Streamlit dashboard

After setup, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\backend\scripts\run.ps1
```

Use the local URL printed in the terminal.

## Check the project

```powershell
npm.cmd --prefix frontend run build
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe backend/tests/dashboard_smoke.py
```

## Deploy to Vercel

From the repository root, stage the frontend, backend, and processed data, then deploy the staged folder.

```powershell
.\.venv\Scripts\python.exe backend/scripts/stage_vercel.py
npx vercel@latest login
npx vercel@latest deploy --cwd .vercel-stage --archive=tgz
```

Select the existing `spectra-fuse-kbpe` project if you are updating the current site. Check the dashboard and `/api/fire/regions` on the same preview domain. To publish a verified build, run the deploy command again with `--prod`. If Vercel blocks a CLI deployment because the Git commit author lacks team access, deploy the linked staging folder from outside the Git checkout or use a team-authorized commit.

## Ask about the dataset

Select a region and open **Ask about the dataset**. These questions work with
the local archive even when OpenAI is unconfigured.

- "What is the oldest data available in the MODIS dataset?"
- "What is the mean monthly fire detections for MODIS in 2024?"

For broader questions and follow-ups, set `OPENAI_API_KEY` and `OPENAI_MODEL`
in the project `.env` or the backend environment and restart FastAPI. Choose
a model that supports Chat Completions and JSON mode. [OpenAI JSON mode documentation](https://developers.openai.com/api/docs/guides/structured-outputs#json-mode)

The model maps the question to lookups. The backend reads the region's archive
and sends the question, recent chat turns and computed evidence to the model.
The API key stays on the backend. Configure access controls at the hosting
layer before enabling a paid API key on a public site.

The answer shows the product, retrieved dates and coverage. Coverage dates come
from downloaded UTC partitions, including days with zero detections. Monthly
averages include complete months with zero detections and omit missing months.
Comparisons use months shared by the requested sensors. Ask for anomaly or
calibration summaries, or try "What was the mean MODIS FRP in February 2024?"
FRP queries support up to 12 months per lookup and use measurements in megawatts
per detection from the available daily files. Specify dates in your question
to limit the lookup independently of the chart's year and sensor filters.

To ingest a period from NASA FIRMS, set `FIRMS_MAP_KEY` and run:

```powershell
.venv/Scripts/python.exe -m backend.fire sync --area "79.5,5.8,82,10" --start 2025-01-01 --end 2025-01-31 --source MODIS_SP --source VIIRS_SNPP_SP --source VIIRS_NOAA20_SP
```

The sync stores daily raw CSV and validated Parquet under `data/` (or
`FIRESCOPE_DATA_DIR`) and rebuilds the monthly table the dashboard and
chat read. Run sync on a machine with writable persistent storage.
