# Start the Rinz Algo backend (run from anywhere). Reads ..\.env from the project root.
Set-Location (Split-Path $PSScriptRoot -Parent)
.\backend\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload --reload-dir backend\app --port 8000
