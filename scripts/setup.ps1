$ErrorActionPreference = 'Stop'
Push-Location (Split-Path -Parent $PSScriptRoot)
try {
    if (!(Test-Path .\.venv\Scripts\python.exe)) {
        python -m venv .venv
        if ($LASTEXITCODE) { throw 'Could not create the Python environment.' }
    }
    & .\.venv\Scripts\python.exe -m pip install -r requirements.txt
    if ($LASTEXITCODE) { throw 'Could not install dependencies.' }
    if (!(Test-Path .env)) { Copy-Item .env.example .env }
} finally { Pop-Location }
