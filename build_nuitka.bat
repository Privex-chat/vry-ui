@echo off
title VRY_UI Build Script
echo ================================================
echo   Building VRY_UI (Standalone)
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
echo ===== Building Standalone Folder Version =====
python -m nuitka main.py ^
  --standalone ^
  --output-dir=build ^
  --remove-output ^
  --assume-yes-for-downloads ^
  --follow-imports ^
  --enable-plugin=pyqt5 ^
  --include-data-file=config.json=./config.json ^
  --include-package=src ^
  --windows-console-mode=disable ^
  --windows-icon-from-ico=icon.ico ^
  --output-filename=VRY_UI.exe ^
  --lto=yes ^
  --jobs=4 ^
  --no-pyi-file

echo.

REM === Copy required files after build ===
echo Copying required resource files...

set "BUILD_DIR=build\main.dist"
set "RESOURCES_DIR=%BUILD_DIR%\resources"

REM Copy Qt/WebEngine resources up one level
for %%F in (
    icudtl.dat
    qtwebengine_resources.pak
    qtwebengine_resources_100p.pak
    qtwebengine_resources_200p.pak
) do (
    if exist "%RESOURCES_DIR%\%%F" (
        copy /Y "%RESOURCES_DIR%\%%F" "%BUILD_DIR%\"
    )
)

REM Copy icon.ico from script run directory into build folder
if exist "icon.ico" (
    copy /Y "icon.ico" "%BUILD_DIR%\"
)

echo Resource copy complete.

echo.
echo ================================================
echo   ✅ Build Complete!
echo   Standalone folder: build\main.dist\
echo ================================================