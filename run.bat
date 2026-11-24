@echo off
REM =========================================================================
REM Automated Data Analyst — Windows one-click launcher
REM
REM What this does:
REM   1. Creates a local Python virtual environment (first run only)
REM   2. Installs backend dependencies
REM   3. Starts the FastAPI backend on http://localhost:8000
REM   4. Waits for the GET /health endpoint to become ready
REM   5. Opens http://localhost:8000 in your default browser
REM
REM Requirements: Python 3.10+ installed and on PATH, PostgreSQL running
REM (only needed once you use the PostgreSQL / SQL Workspace screens).
REM =========================================================================

setlocal

echo.
echo ==========================================================
echo  Automated Data Analyst — starting up
echo ==========================================================
echo.

if not exist ".venv" (
    echo [1/4] Creating virtual environment...
    python -m venv .venv
) else (
    echo [1/4] Virtual environment already exists, skipping.
)

call .venv\Scripts\activate.bat

echo [2/4] Installing/updating dependencies (this may take a minute the first time)...
python -m pip install --upgrade pip >nul
pip install -r requirements.txt

if not exist ".env" (
    echo [3/4] No .env found — copying .env.example to .env
    copy .env.example .env >nul
    echo         Edit .env with your PostgreSQL password before using the Database screen.
) else (
    echo [3/4] .env already exists, skipping.
)

echo [4/4] Starting backend at http://localhost:8000 ...
start "Automated Data Analyst - Backend" cmd /k "call .venv\Scripts\activate.bat && uvicorn backend.main:app --reload --port 8000"

echo Waiting for backend health check at http://localhost:8000/health ...
powershell -NoProfile -Command "$ready=$false; for ($i=0; $i -lt 30; $i++) { try { $res = Invoke-RestMethod -Uri 'http://localhost:8000/health' -TimeoutSec 1 -ErrorAction Stop; if ($res.status -eq 'healthy') { $ready=$true; break } } catch {} Start-Sleep -Milliseconds 500 }; if (-not $ready) { Write-Warning 'Backend took longer than expected to respond. Opening browser anyway...' }"

echo Opening frontend at http://localhost:8000 ...
start "" "http://localhost:8000"

echo.
echo Backend running in a separate window. Close that window to stop the server.
echo Frontend opened in your browser at http://localhost:8000
echo.
pause
