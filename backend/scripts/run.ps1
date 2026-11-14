$ErrorActionPreference = 'Stop'
Push-Location (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
try {
    & .\.venv\Scripts\python.exe -m streamlit run backend/app.py --server.address 127.0.0.1 --browser.gatherUsageStats false
    if ($LASTEXITCODE) { throw 'FireScope exited with an error.' }
} finally { Pop-Location }
