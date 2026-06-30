@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "SCRIPT_PATH=%SCRIPT_DIR%ping-tuckz-gui.py"

pushd "%SCRIPT_DIR%" >nul

where pythonw >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    start "" pythonw "%SCRIPT_PATH%"
    set "EXIT_CODE=0"
) else (
    where pyw >nul 2>nul
    if %ERRORLEVEL% EQU 0 (
        start "" pyw -3 "%SCRIPT_PATH%"
        set "EXIT_CODE=0"
    ) else (
        where python >nul 2>nul
        if %ERRORLEVEL% EQU 0 (
            python "%SCRIPT_PATH%"
            set "EXIT_CODE=%ERRORLEVEL%"
        ) else (
            echo Error: Python was not found. Install Python 3 or add it to PATH.
            set "EXIT_CODE=1"
        )
    )
)

popd >nul
exit /b %EXIT_CODE%
