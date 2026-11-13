# Start the Rinz Algo backend (run from anywhere). Reads ..\.env from the project root.
#   .\backend\start.ps1        -> this PC only (127.0.0.1)
#   .\backend\start.ps1 -Lan   -> also reachable from your phone / home network; refuses to start without APP_ACCESS_TOKEN
param([switch]$Lan)
Set-Location (Split-Path $PSScriptRoot -Parent)
$bind = "127.0.0.1"
if ($Lan) {
    $hasToken = (Test-Path .env) -and (Select-String -Path .env -Pattern '^\s*APP_ACCESS_TOKEN\s*=\s*\S{16,}' -Quiet)
    if (-not $hasToken) {
        Write-Host "Refusing to open the backend to the network: set APP_ACCESS_TOKEN (16+ characters) in .env first." -ForegroundColor Red
        Write-Host "The backend can start and stop trading sessions and press the kill switch; it must not be open without a token."
        exit 1
    }
    $bind = "0.0.0.0"
    Write-Host "Backend reachable on your network at port 8000 (token required)." -ForegroundColor Yellow
}
.\backend\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload --reload-dir backend\app --host $bind --port 8000
