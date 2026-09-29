@echo off
rem One-click start for Windows: sets up everything on first run, then opens the app.
setlocal
cd /d "%~dp0"
if "%PORT%"=="" set PORT=8000

where py >nul 2>nul && (set PY=py -3) || (set PY=python)

if not exist ".venv\Scripts\python.exe" (
    echo [ClinicFlow] First run: creating the Python environment...
    %PY% -m venv .venv || goto :nopython
    echo [ClinicFlow] Installing dependencies ^(1-2 minutes^)...
    ".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
    ".venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt || goto :fail
)
if not exist ".env" copy ".env.example" ".env" >nul

echo.
echo [ClinicFlow] Starting on http://localhost:%PORT%
echo [ClinicFlow] Optional: paste a free Gemini key in .env (GEMINI_API_KEY=...) for free conversation.
echo [ClinicFlow] Close this window to stop.
echo.
if "%NO_BROWSER%"=="" start "" /b cmd /c "timeout /t 4 >nul & start http://localhost:%PORT%"
".venv\Scripts\python.exe" -m uvicorn app.main:app --port %PORT%
goto :eof

:nopython
echo [ClinicFlow] Python 3.12+ was not found. Install it from https://www.python.org/downloads/ and run this again.
pause
exit /b 1

:fail
echo [ClinicFlow] Installing dependencies failed. See the messages above.
pause
exit /b 1
