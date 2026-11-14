$ErrorActionPreference = 'Stop'
Push-Location (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
try {
    $python = '.\.venv\Scripts\python.exe'
    for ($attempt = 1; $attempt -le 12; $attempt++) {
        $result = & $python -m backend.fire sync --area '79.5,5.8,82,10' --start 2018-01-01 --end 2023-12-31 2>&1 |
            ForEach-Object { Write-Host $_; $_.ToString() }
        if ($LASTEXITCODE -eq 0) {
            & $python backend/scripts/pilot_report.py
            exit $LASTEXITCODE
        }
        if ($attempt -eq 12 -or ($result -join "`n") -notmatch 'transaction limit exceeded|FIRMS returned HTTP (401|403)') {
            throw 'Pilot sync stopped. Review the FIRMS message above and rerun to resume.'
        }
        Write-Host 'Waiting five minutes before resuming the pilot.'
        Start-Sleep -Seconds 300
    }
} finally { Pop-Location }
