@echo off
setlocal EnableExtensions

rem Quick Vite launcher for Windows.
rem Run npm install in frontend\ once before using this script.

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "FRONTEND_DIR=%ROOT%\frontend"

where npm >nul 2>nul
if errorlevel 1 (
  echo [FAIL] npm was not found on PATH.
  echo [HINT] Install Node.js LTS, then run:
  echo        cd "%FRONTEND_DIR%"
  echo        npm install
  exit /b 1
)

if not exist "%FRONTEND_DIR%\node_modules" (
  echo [FAIL] frontend\node_modules was not found.
  echo [HINT] Install frontend dependencies first:
  echo        cd "%FRONTEND_DIR%"
  echo        npm install
  exit /b 1
)

echo.
echo ============================================================
echo  Investment Tracker Frontend
echo ============================================================
echo [INFO] Frontend dir : %FRONTEND_DIR%
echo [INFO] URL          : http://127.0.0.1:5173
echo [INFO] Stop         : Press Ctrl+C
echo.

pushd "%FRONTEND_DIR%" || exit /b 1
npm run dev
set "EXIT_CODE=%ERRORLEVEL%"
popd
exit /b %EXIT_CODE%
