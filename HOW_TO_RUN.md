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
