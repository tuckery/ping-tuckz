@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
set "SCRIPT_PATH=%SCRIPT_DIR%ping-tuckz-gui.py"
set "LAUNCHER_PATH=%SCRIPT_DIR%launch-gui.py"
set "BOOTSTRAP_PATH=%SCRIPT_DIR%bootstrap-python.bat"
set "LOG_DIR=%SCRIPT_DIR%Logs"
set "LOG_PATH=%LOG_DIR%\ping-tuckz-gui.log"

pushd "%SCRIPT_DIR%" >nul

call "%BOOTSTRAP_PATH%" gui
if errorlevel 1 (
    set "EXIT_CODE=!ERRORLEVEL!"
    echo.
    echo Ping Tuckz could not start.
    echo Resolve the Python setup issue above, then run Ping Tuckz again.
    echo.
    pause
) else (
    if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
    start "" "!PING_TUCKZ_PYTHON_EXE!" "%LAUNCHER_PATH%" "%SCRIPT_PATH%" "%LOG_PATH%"
    set "EXIT_CODE=!ERRORLEVEL!"
    if not "!EXIT_CODE!"=="0" (
        echo.
        echo Ping Tuckz could not launch Python.
        echo Attempted:
        echo "!PING_TUCKZ_PYTHON_EXE!" "%LAUNCHER_PATH%"
        echo.
        pause
    )
)

popd >nul
exit /b !EXIT_CODE!
