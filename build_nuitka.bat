@echo off
title VRY_UI Build Script
echo ================================================
echo   Building VRY_UI (Onefile EXE)
echo ================================================
echo.

REM Ensure we're in the script directory
cd /d "%~dp0"

REM Clean old build folder if exists
if exist build (
    echo Removing old build folder...
    rmdir /s /q build
)
mkdir build

echo.
echo ===== Building Onefile EXE Version =====
python -m nuitka main.py ^
  --onefile ^
  --output-dir=build ^
  --remove-output ^
  --assume-yes-for-downloads ^
  --follow-imports ^
  --enable-plugin=pyqt6 ^
  --include-data-file=config.json=./config.json ^
  --include-package=src ^
  --include-package=asyncio ^
  --include-package=websockets ^
  --include-package=concurrent.futures ^
  --windows-console-mode=disable ^
  --windows-icon-from-ico=icon.ico ^
  --output-filename=VRY_UI.exe ^
  --lto=yes ^
  --jobs=4 ^
  --no-pyi-file ^
  --python-flag=no_site

echo.
echo ================================================
echo   ✅ Build Complete!
echo   Executable created at: build\VRY_UI.exe
echo ================================================
pause