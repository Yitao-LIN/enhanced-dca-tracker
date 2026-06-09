@echo off
setlocal EnableExtensions EnableDelayedExpansion

rem Project test runner for Windows.
rem Keep this file updated as new stable automated checks are added.

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

set "BACKEND_DIR=%ROOT%\backend"
set "TESTS_DIR=%ROOT%\tests"
set "LOCAL_DIR=%ROOT%\.local"
set "PYTHON=%BACKEND_DIR%\.venv\Scripts\python.exe"
set "ALEMBIC=%BACKEND_DIR%\.venv\Scripts\alembic.exe"
set "TEST_DB=%LOCAL_DIR%\migration-smoke-bat.sqlite3"
set "TEST_DB_PATH=%TEST_DB%"
set "DB_URL_PATH=%TEST_DB:\=/%"

echo.
echo ============================================================
echo  Investment Tracker Test Runner
echo ============================================================
echo [INFO] Repository root : %ROOT%
echo [INFO] Backend dir     : %BACKEND_DIR%
echo [INFO] Tests dir       : %TESTS_DIR%
echo [INFO] Python          : %PYTHON%
echo [INFO] Alembic         : %ALEMBIC%
echo.

if not exist "%PYTHON%" (
  echo [FAIL] Python executable was not found.
  echo [HINT] Create the backend virtual environment and install requirements first:
  echo        cd "%BACKEND_DIR%"
  echo        python -m venv .venv
  echo        .\.venv\Scripts\python.exe -m pip install -r requirements.txt
  exit /b 1
)

if not exist "%ALEMBIC%" (
  echo [FAIL] Alembic executable was not found in the backend virtual environment.
  echo [HINT] Install backend requirements, then run this script again.
  exit /b 1
)

if not exist "%LOCAL_DIR%" (
  echo [INFO] Creating local scratch directory: %LOCAL_DIR%
  mkdir "%LOCAL_DIR%"
  if errorlevel 1 (
    echo [FAIL] Could not create local scratch directory.
    exit /b 1
  )
)

set "PYTHONPATH=%BACKEND_DIR%"

call :section "1/3 Unit and repository tests"
echo [ENV] PYTHONPATH=%PYTHONPATH%
echo [CMD] "%PYTHON%" -m unittest discover -s "%TESTS_DIR%" -v
"%PYTHON%" -m unittest discover -s "%TESTS_DIR%" -v 2>&1
if errorlevel 1 goto :fail
echo [PASS] Unit and repository tests completed.

call :section "2/3 Python compile check"
echo [CMD] "%PYTHON%" -m compileall "%BACKEND_DIR%\app" "%BACKEND_DIR%\alembic" "%TESTS_DIR%"
"%PYTHON%" -m compileall "%BACKEND_DIR%\app" "%BACKEND_DIR%\alembic" "%TESTS_DIR%" 2>&1
if errorlevel 1 goto :fail
echo [PASS] Compile check completed.

call :section "3/3 Alembic fresh database migration smoke test"
if exist "%TEST_DB%" (
  echo [INFO] Removing previous smoke database: %TEST_DB%
  del /f /q "%TEST_DB%"
  if errorlevel 1 goto :fail
)

set "INVESTMENT_TRACKER_DATABASE_URL=sqlite:///%DB_URL_PATH%"
echo [ENV] INVESTMENT_TRACKER_DATABASE_URL=%INVESTMENT_TRACKER_DATABASE_URL%
echo [CMD] "%ALEMBIC%" -c "%BACKEND_DIR%\alembic.ini" upgrade head
"%ALEMBIC%" -c "%BACKEND_DIR%\alembic.ini" upgrade head 2>&1
if errorlevel 1 goto :fail

echo [CMD] Inspect migration revision and expected tables
"%PYTHON%" -c "import os, sqlite3; expected={'accounts','alembic_version','dca_settings','hidden_securities','import_sessions','market_price_history','market_prices','portfolios','security_mappings','transaction_fingerprints','transactions'}; con=sqlite3.connect(os.environ['TEST_DB_PATH']); version=con.execute('select version_num from alembic_version').fetchone(); tables=[row[0] for row in con.execute('select name from sqlite_master where type=? order by name', ('table',))]; missing=sorted(expected-set(tables)); print('alembic_version =', version); print('tables = ' + ', '.join(tables)); print('missing tables = ' + (', '.join(missing) if missing else 'none')); raise SystemExit(1 if missing or not version else 0)" 2>&1
if errorlevel 1 goto :fail
echo [PASS] Alembic migration smoke test completed.

call :section "Summary"
echo [PASS] All automated checks passed.
echo [INFO] Manual/API/frontend smoke tests are documented in docs\TESTING.md.
exit /b 0

:section
echo.
echo ============================================================
echo  %~1
echo ============================================================
exit /b 0

:fail
echo.
echo ============================================================
echo  Test runner failed
echo ============================================================
echo [FAIL] Last command exited with code %ERRORLEVEL%.
echo [HINT] Scroll up to the nearest traceback, SyntaxError, failed assertion, or Alembic message.
echo [HINT] The detailed purpose and expected output for each check live in docs\TESTING.md.
exit /b %ERRORLEVEL%
