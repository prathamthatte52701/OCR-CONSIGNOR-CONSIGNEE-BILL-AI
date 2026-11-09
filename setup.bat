@echo off
rem One-time (and safe to repeat) setup for THE MAIN OCR (Consignor / Consignee).
rem Needs Python 3.12 and Node.js 20.19+ (or 22.12+). Never overwrites backend\.env.
setlocal
set "ROOT=%~dp0"
set "RC=0"
set "PY=%ROOT%venv\Scripts\python.exe"

set "PYX="
where py >nul 2>nul
if not errorlevel 1 (
  py -3.12 --version >nul 2>nul
  if not errorlevel 1 set "PYX=py -3.12"
)
if not defined PYX (
  python --version 2>&1 | "%SystemRoot%\System32\find.exe" "Python 3.12" >nul
  if not errorlevel 1 set "PYX=python"
)
if not exist "%PY%" if not defined PYX (
  echo ERROR: Python 3.12 was not found. Install it from python.org, then run setup.bat again.
  set "RC=1"
  goto done
)
where node >nul 2>nul
if errorlevel 1 (
  echo ERROR: Node.js was not found. Install Node 20.19+ or 22.12+ from nodejs.org.
  set "RC=1"
  goto done
)
where npm >nul 2>nul
if errorlevel 1 (
  echo ERROR: npm was not found. Reinstall Node.js 20.19+ or 22.12+.
  set "RC=1"
  goto done
)
node -e "var v=process.versions.node.split('.').map(Number);var m=v[0],n=v[1];process.exit(((m==20&&n>=19)||(m==22&&n>=12)||m>22)?0:1)"
if errorlevel 1 (
  echo ERROR: Node.js is too old. Vite 8 needs Node 20.19+ or 22.12+.
  set "RC=1"
  goto done
)

echo [1/4] Python virtual environment...
if exist "%PY%" (
  echo venv already exists, keeping it.
) else (
  %PYX% -m venv "%ROOT%venv"
  if errorlevel 1 (
    echo ERROR: could not create the venv.
    set "RC=1"
    goto done
  )
)

echo [2/4] Installing backend packages (the first time this is big and slow)...
"%PY%" -m pip install -r "%ROOT%requirements.txt"
if errorlevel 1 (
  echo ERROR: backend package install failed.
  set "RC=1"
  goto done
)

echo [3/4] Installing the user app and admin app packages...
set "APP=frontend"
call :webapp
if not "%RC%"=="0" goto done
set "APP=admin"
call :webapp
if not "%RC%"=="0" goto done

echo [4/4] Settings file...
if exist "%ROOT%backend\.env" (
  echo backend\.env already exists, left untouched.
) else if exist "%ROOT%backend\.env.example" (
  copy "%ROOT%backend\.env.example" "%ROOT%backend\.env" >nul
  echo Created backend\.env from backend\.env.example.
  echo FILL IT IN before starting: MONGO_URI, GROQ_API_KEYS, JWT_SECRET ^(at least 32 characters^),
  echo and ADMIN_1_EMAIL / ADMIN_1_USERNAME / ADMIN_1_PASSWORD for the first admin.
) else (
  echo WARNING: backend\.env and backend\.env.example are both missing. Create backend\.env.
)

echo.
echo Setup finished. Next: fill backend\.env, run the first-admin script once:
echo   venv\Scripts\python.exe -m app.scripts.seed_admin   ^(from the backend folder^)
echo then run start.bat
goto done

:webapp
echo   npm ci in %APP% ...
pushd "%ROOT%%APP%"
if errorlevel 1 (
  echo ERROR: folder %APP% not found.
  set "RC=1"
  exit /b 1
)
call npm ci
if errorlevel 1 (
  echo ERROR: npm ci failed in %APP%.
  popd
  set "RC=1"
  exit /b 1
)
popd
exit /b 0

:done
echo "%cmdcmdline:"='%" | "%SystemRoot%\System32\find.exe" /i "/c ''" >nul && pause
exit /b %RC%
