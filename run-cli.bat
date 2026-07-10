@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
set "SCRIPT_PATH=%SCRIPT_DIR%ping_tuckz_core.py"
set "BOOTSTRAP_PATH=%SCRIPT_DIR%bootstrap-python.bat"

pushd "%SCRIPT_DIR%" >nul

call "%BOOTSTRAP_PATH%" cli
if errorlevel 1 (
    set "EXIT_CODE=!ERRORLEVEL!"
) else (
    call "!PING_TUCKZ_PYTHON_EXE!" "%SCRIPT_PATH%" %*
    set "EXIT_CODE=!ERRORLEVEL!"
)

popd >nul
exit /b !EXIT_CODE!
