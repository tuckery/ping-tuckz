@echo off
rem Finds a usable Python 3.12+ runtime for Ping Tuckz.
rem If Python is missing, prompts before installing Python with winget.

set "PING_TUCKZ_PYTHON_EXE="
set "PING_TUCKZ_PYTHON_CONSOLE_EXE="
set "PING_TUCKZ_MODE=%~1"

if /I not "%PING_TUCKZ_MODE%"=="gui" if /I not "%PING_TUCKZ_MODE%"=="cli" (
    echo Usage: bootstrap-python.bat gui^|cli
    exit /b 2
)

call :find_python "%PING_TUCKZ_MODE%"
if not errorlevel 1 exit /b 0

echo.
echo Ping Tuckz requires Python 3.12 or newer.
if /I "%PING_TUCKZ_MODE%"=="gui" (
    echo The GUI also requires tkinter, which is included with the normal Windows Python installer.
)
echo.
choice /C YN /N /M "Install Python 3.12 now using winget? [Y/N] "
if errorlevel 2 (
    echo.
    echo Python was not installed. Install Python 3.12 or newer, then run Ping Tuckz again.
    echo Recommended package: Python.Python.3.12
    echo Download: https://www.python.org/downloads/windows/
    exit /b 1
)

where winget >nul 2>nul
if errorlevel 1 (
    echo.
    echo winget was not found on this machine.
    echo Install Python 3.12 or newer manually, then run Ping Tuckz again.
    echo Download: https://www.python.org/downloads/windows/
    exit /b 1
)

echo.
echo Installing Python 3.12 with winget...
winget install --id Python.Python.3.12 -e --source winget --scope user --accept-source-agreements --accept-package-agreements
if errorlevel 1 (
    echo.
    echo Python installation failed or was cancelled.
    exit /b 1
)

call :find_python "%PING_TUCKZ_MODE%"
if not errorlevel 1 exit /b 0

echo.
echo Python was installed, but this terminal cannot find it yet.
echo Close this window and run Ping Tuckz again.
exit /b 1

:find_python
set "PING_TUCKZ_FIND_MODE=%~1"

for /f "delims=" %%P in ('where python 2^>nul') do (
    call :try_python "%%P" "%PING_TUCKZ_FIND_MODE%"
    if not errorlevel 1 exit /b 0
)

for /f "delims=" %%P in ('py -3 -c "import sys; print(sys.executable)" 2^>nul') do (
    call :try_python "%%P" "%PING_TUCKZ_FIND_MODE%"
    if not errorlevel 1 exit /b 0
)

for %%P in (
    "%LocalAppData%\Programs\Python\Python314\python.exe"
    "%LocalAppData%\Programs\Python\Python313\python.exe"
    "%LocalAppData%\Programs\Python\Python312\python.exe"
    "%ProgramFiles%\Python314\python.exe"
    "%ProgramFiles%\Python313\python.exe"
    "%ProgramFiles%\Python312\python.exe"
) do (
    if exist "%%~P" (
        call :try_python "%%~P" "%PING_TUCKZ_FIND_MODE%"
        if not errorlevel 1 exit /b 0
    )
)

exit /b 1

:try_python
set "PING_TUCKZ_CANDIDATE=%~1"
set "PING_TUCKZ_TRY_MODE=%~2"

if not exist "%PING_TUCKZ_CANDIDATE%" exit /b 1
if /I not "%PING_TUCKZ_CANDIDATE:\Microsoft\WindowsApps\=%"=="%PING_TUCKZ_CANDIDATE%" exit /b 1

call "%PING_TUCKZ_CANDIDATE%" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)" >nul 2>nul
if errorlevel 1 exit /b 1

if /I "%PING_TUCKZ_TRY_MODE%"=="gui" (
    call "%PING_TUCKZ_CANDIDATE%" -c "import tkinter" >nul 2>nul
    if errorlevel 1 exit /b 1
)

if /I "%PING_TUCKZ_TRY_MODE%"=="gui" (
    set "PING_TUCKZ_PYTHON_CONSOLE_EXE=%PING_TUCKZ_CANDIDATE%"
    for %%I in ("%PING_TUCKZ_CANDIDATE%") do (
        if exist "%%~dpIpythonw.exe" (
            set "PING_TUCKZ_PYTHON_EXE=%%~dpIpythonw.exe"
        ) else (
            set "PING_TUCKZ_PYTHON_EXE=%%~fI"
        )
    )
) else (
    set "PING_TUCKZ_PYTHON_EXE=%PING_TUCKZ_CANDIDATE%"
    set "PING_TUCKZ_PYTHON_CONSOLE_EXE=%PING_TUCKZ_CANDIDATE%"
)

exit /b 0
