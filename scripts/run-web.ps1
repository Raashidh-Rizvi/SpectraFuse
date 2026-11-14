param([int]$Port = 8001)
$ErrorActionPreference = 'Stop'
if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
    throw "Port $Port is already in use. Choose another port with -Port 8002."
}
Push-Location (Split-Path -Parent $PSScriptRoot)
try {
    Push-Location frontend
    try {
        npm ci
        if ($LASTEXITCODE) { throw 'Could not install frontend dependencies.' }
        npm run build
        if ($LASTEXITCODE) { throw 'Could not build FireScope.' }
    } finally { Pop-Location }
    & .\.venv\Scripts\python.exe -m uvicorn api:app --host 127.0.0.1 --port $Port
    if ($LASTEXITCODE) { throw 'FireScope API exited with an error.' }
} finally { Pop-Location }
