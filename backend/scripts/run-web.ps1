param([int]$Port = 8001)
$ErrorActionPreference = 'Stop'
if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
    throw "Port $Port is already in use. Choose another port with -Port 8002."
}
Push-Location (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
try {
    Push-Location frontend
    try {
        npm ci
        if ($LASTEXITCODE) { throw 'Could not install frontend dependencies.' }
        npm run build
        if ($LASTEXITCODE) { throw 'Could not build SpectraFuse.' }
    } finally { Pop-Location }
    $pythonCmd = if (Test-Path .\.venv\Scripts\python.exe) { ".\.venv\Scripts\python.exe" } else { "python" }
    & $pythonCmd -m uvicorn backend.main:app --host 127.0.0.1 --port $Port
    if ($LASTEXITCODE) { throw 'SpectraFuse API exited with an error.' }
} finally { Pop-Location }
