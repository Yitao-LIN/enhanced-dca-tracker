@echo off
setlocal EnableExtensions EnableDelayedExpansion

rem Quick FastAPI launcher for local testing.
rem Optional first argument: port number. Example: start_backend.bat 8766

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

set "BACKEND_DIR=%ROOT%\backend"
set "LOCAL_DIR=%ROOT%\.local"
set "PYTHON=%BACKEND_DIR%\.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
  echo [FAIL] Backend Python executable was not found:
  echo        %PYTHON%
  echo [HINT] Create the backend virtual environment and install requirements:
  echo        cd "%BACKEND_DIR%"
  echo        python -m venv .venv
  echo        .\.venv\Scripts\python.exe -m pip install -r requirements.txt
  exit /b 1
)

if not exist "%LOCAL_DIR%" (
  mkdir "%LOCAL_DIR%"
  if errorlevel 1 (
    echo [FAIL] Could not create local scratch directory:
    echo        %LOCAL_DIR%
    exit /b 1
  )
)

if "%TRACKER_BACKEND_HOST%"=="" set "TRACKER_BACKEND_HOST=127.0.0.1"
if "%TRACKER_BACKEND_PORT%"=="" set "TRACKER_BACKEND_PORT=8000"
if not "%~1"=="" set "TRACKER_BACKEND_PORT=%~1"

if "%INVESTMENT_TRACKER_DATABASE_URL%"=="" (
  set "DEFAULT_DB=%LOCAL_DIR%\tracker-dev.sqlite3"
  set "DB_URL_PATH=!DEFAULT_DB:\=/!"
  set "INVESTMENT_TRACKER_DATABASE_URL=sqlite:///!DB_URL_PATH!"
)

set "PYTHONPATH=%BACKEND_DIR%"

echo.
echo ============================================================
echo  Investment Tracker Backend
echo ============================================================
echo [INFO] Backend dir : %BACKEND_DIR%
echo [INFO] Python      : %PYTHON%
echo [INFO] Database    : %INVESTMENT_TRACKER_DATABASE_URL%
echo [INFO] URL         : http://%TRACKER_BACKEND_HOST%:%TRACKER_BACKEND_PORT%
echo [INFO] Health      : http://%TRACKER_BACKEND_HOST%:%TRACKER_BACKEND_PORT%/api/health
echo [INFO] Stop        : Press Ctrl+C
echo.

pushd "%BACKEND_DIR%" || exit /b 1
"%PYTHON%" -m uvicorn app.main:app --host "%TRACKER_BACKEND_HOST%" --port "%TRACKER_BACKEND_PORT%" --reload
set "EXIT_CODE=%ERRORLEVEL%"
popd
exit /b %EXIT_CODE%
