@echo off
setlocal
cd /d "%~dp0"

echo ==========================================
echo  McOsuTracker - build from build.spec
echo ==========================================
echo.

if not exist "build.spec" (
    echo [ERROR] build.spec was not found in:
    echo         %~dp0
    echo.
    pause
    exit /b 1
)

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python was not found in PATH.
    echo         Install Python or add it to PATH.
    echo.
    pause
    exit /b 1
)

python -m PyInstaller --version >nul 2>nul
if errorlevel 1 (
    echo [ERROR] PyInstaller is not installed.
    echo         Run: python -m pip install pyinstaller
    echo.
    pause
    exit /b 1
)

echo [1/1] Building McOsuTracker.exe...
echo.
python -m PyInstaller --clean --noconfirm build.spec
if errorlevel 1 (
    echo.
    echo [ERROR] Build failed. See the log above.
    echo.
    pause
    exit /b 1
)

echo.
echo ==========================================
echo  Build complete
echo  %~dp0dist\McOsuTracker.exe
echo ==========================================
echo.

if exist "%~dp0dist\McOsuTracker.exe" (
    explorer /select,"%~dp0dist\McOsuTracker.exe"
)

pause
exit /b 0
