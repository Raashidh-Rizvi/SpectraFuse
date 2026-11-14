$ErrorActionPreference = 'Stop'
Push-Location (Split-Path -Parent $PSScriptRoot)
try {
    $python = '.\.venv\Scripts\python.exe'
    foreach ($product in 'MODIS_SP', 'VIIRS_SNPP_SP', 'VIIRS_NOAA20_SP') {
        $ErrorActionPreference = 'Continue'
        for ($attempt = 1; $attempt -le 12; $attempt++) {
            $result = & $python fire.py sync --source $product --area '79.5,5.8,82,10' --start 2000-11-01 --end (Get-Date -Format yyyy-MM-dd) 2>&1 |
                ForEach-Object { Write-Host $_; $_.ToString() }
            if ($LASTEXITCODE -eq 0) { break }
            if ($attempt -eq 12 -or ($result -join "`n") -notmatch 'transaction limit exceeded|FIRMS returned HTTP (401|403)') {
                throw "Historical sync stopped for $product. Rerun to resume."
            }
            Start-Sleep -Seconds 300
        }
    }
} finally { Pop-Location }
