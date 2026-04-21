@echo off
title VRY_UI Build Script
echo ================================================
echo           Building VRY_UI
echo        (Optimized for faster builds)
echo ================================================
echo.

cd /d "%~dp0"

echo [1/4] Checking build dependencies...
pip show zstandard >nul 2>&1 || (
    echo   Installing zstandard...
    pip install zstandard -q
)
pip show ordered-set >nul 2>&1 || (
    echo   Installing ordered-set...
    pip install ordered-set -q
)

for /f "tokens=2 delims==" %%i in (
    'wmic cpu get NumberOfLogicalProcessors /value ^| find "="'
) do set CPU_COUNT=%%i
if "%CPU_COUNT%"=="" set CPU_COUNT=4
echo [2/4] Using %CPU_COUNT% CPU threads.

echo [3/4] Cleaning old build...
if exist build rmdir /s /q build
mkdir build

echo [4/4] Compiling...
echo.

set QTWEBENGINE_CHROMIUM_FLAGS=--disable-logging --log-level=3

python -m nuitka main.py ^
  --onefile ^
  --output-dir=build ^
  --output-filename=VRY_UI.exe ^
  --remove-output ^
  --assume-yes-for-downloads ^
  --enable-plugin=pyside6 ^
  --include-data-file=config.json=./config.json ^
  --include-package=src ^
  --include-package=asyncio ^
  --include-package=websockets ^
  --include-package=concurrent.futures ^
  --lto=no ^
  --jobs=%CPU_COUNT% ^
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
  --nofollow-import-to=PySide6.QtCharts ^
  --nofollow-import-to=PySide6.Qt3DCore ^
  --nofollow-import-to=PySide6.Qt3DRender ^
  --nofollow-import-to=PySide6.Qt3DInput ^
  --nofollow-import-to=PySide6.Qt3DAnimation ^
  --nofollow-import-to=PySide6.Qt3DExtras ^
  --nofollow-import-to=tkinter ^
  --nofollow-import-to=unittest ^
  --nofollow-import-to=distutils ^
  --nofollow-import-to=lib2to3 ^
  --nofollow-import-to=pydoc ^
  --nofollow-import-to=doctest ^
  --nofollow-import-to=turtle ^
  --nofollow-import-to=curses ^
  --nofollow-import-to=idlelib ^
  --nofollow-import-to=ensurepip ^
  --windows-console-mode=disable ^
  --windows-icon-from-ico=icon.ico ^
  --python-flag=no_site

if %ERRORLEVEL% neq 0 (
    echo.
    echo ================================================
    echo    Build FAILED  ^(exit code %ERRORLEVEL%^)
    echo ================================================
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo ================================================
echo            Build Complete!
echo   Executable: build\VRY_UI.exe
echo ================================================
pause
