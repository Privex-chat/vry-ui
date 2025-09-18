@echo off
title VRY_UI Build Script
echo ================================================
echo           Building VRY_UI 
echo   (Optimized for smaller binary size)
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
echo ===== Building =====
REM Prevent QtWebEngine from creating debug.log
set QTWEBENGINE_CHROMIUM_FLAGS=--disable-logging --log-level=3
python -m nuitka main.py ^
  --onefile ^
  --output-dir=build ^
  --remove-output ^
  --assume-yes-for-downloads ^
  --follow-imports ^
  --enable-plugin=pyside6 ^
  --include-data-file=config.json=./config.json ^
  --include-package=src ^
  --include-package=asyncio ^
  --include-package=websockets ^
  --include-package=concurrent.futures ^
  --noinclude-qt-translations ^
  --nofollow-import-to=PySide6.QtBluetooth ^
  --nofollow-import-to=PySide6.QtDBus ^
  --nofollow-import-to=PySide6.QtDesigner ^
  --nofollow-import-to=PySide6.QtHelp ^
  --nofollow-import-to=PySide6.QtLocation ^
  --nofollow-import-to=PySide6.QtMultimedia ^
  --nofollow-import-to=PySide6.QtMultimediaWidgets ^
  --nofollow-import-to=PySide6.QtNfc ^
  --nofollow-import-to=PySide6.QtOpenGL ^
  --nofollow-import-to=PySide6.QtOpenGLWidgets ^
  --nofollow-import-to=PySide6.QtPositioning ^
  --nofollow-import-to=PySide6.QtQuick ^
  --nofollow-import-to=PySide6.QtQuickWidgets ^
  --nofollow-import-to=PySide6.QtRemoteObjects ^
  --nofollow-import-to=PySide6.QtScxml ^
  --nofollow-import-to=PySide6.QtSensors ^
  --nofollow-import-to=PySide6.QtSerialPort ^
  --nofollow-import-to=PySide6.QtSpatialAudio ^
  --nofollow-import-to=PySide6.QtSql ^
  --nofollow-import-to=PySide6.QtStateMachine ^
  --nofollow-import-to=PySide6.QtTest ^
  --nofollow-import-to=PySide6.QtUiTools ^
  --nofollow-import-to=PySide6.QtXml ^
  --windows-console-mode=disable ^
  --windows-icon-from-ico=icon.ico ^
  --output-filename=VRY_UI.exe ^
  --lto=yes ^
  --jobs=4 ^
  --no-pyi-file ^
  --python-flag=no_site

echo.
echo ================================================
echo            ✅ Build Complete!
echo   Executable created at: build\VRY_UI.exe
echo ================================================
pause