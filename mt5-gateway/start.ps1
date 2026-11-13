# Start the MT5 gateway. Use -Host 0.0.0.0 only if the backend runs in Docker.
param([string]$BindHost = "127.0.0.1", [int]$Port = 9000)
Set-Location $PSScriptRoot
.\.venv\Scripts\python.exe -m uvicorn gateway:app --host $BindHost --port $Port
