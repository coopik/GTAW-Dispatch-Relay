@echo off
REM ============================================================
REM  911 Dispatch Relay - one-click Windows build
REM  Produces:  dist\911 Dispatch Relay\  (standalone app)
REM             installer_output\911DispatchRelay-Setup-1.0.0.exe (if Inno Setup installed)
REM ============================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo(
echo === 911 Dispatch Relay - build ===
echo(

REM Prefer the 'py' launcher, fall back to python.
where py >nul 2>nul
if %errorlevel%==0 (set "PY=py") else (set "PY=python")

echo [1/4] Creating an isolated build environment...
%PY% -m venv .buildenv || goto :err
call .buildenv\Scripts\activate.bat || goto :err

echo [2/4] Installing dependencies + PyInstaller...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt || goto :err
python -m pip install pyinstaller || goto :err

echo [3/4] Building the application with PyInstaller...
pyinstaller --noconfirm --clean "911DispatchRelay.spec" || goto :err

echo [4/4] Building the installer with Inno Setup (if installed)...
set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if defined ISCC (
  "!ISCC!" "installer.iss" || goto :err
  echo(
  echo   Installer created in:  installer_output\
) else (
  echo(
  echo   Inno Setup 6 not found - skipping installer step.
  echo   The ready-to-run app is in:  "dist\911 Dispatch Relay\"
  echo   To also get a setup.exe, install Inno Setup 6 from
  echo   https://jrsoftware.org/isdl.php  and run build.bat again.
)

echo(
echo DONE.
echo(
deactivate
goto :eof

:err
echo(
echo *** BUILD FAILED - see the messages above. ***
exit /b 1
