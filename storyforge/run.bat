@echo off
setlocal enabledelayedexpansion
title StoryForge
cd /d "%~dp0"

REM Clear variables that can confuse Python and cause the
REM "Could not find platform independent libraries" error
set "PYTHONHOME="
set "PYTHONPATH="

echo ==================================================
echo   StoryForge - one-click launcher
echo ==================================================
echo.

REM ---------- 1. Find a WORKING Python (install if needed) ----------
call :findpy
if not defined PY (
    echo No working Python found. Installing Python 3.12 automatically...
    where winget >nul 2>nul
    if not errorlevel 1 (
        winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
    )
    call :findpy
)
if not defined PY goto :nopython
echo Python OK: %PY%
goto :havepython

:findpy
set "PY="
python -c "import venv,ssl,encodings,sys;sys.exit(0 if (3,10)<=sys.version_info[:2]<=(3,13) else 1)" >nul 2>nul && set "PY=python"
if defined PY exit /b 0
py -3 -c "import venv,ssl,encodings,sys;sys.exit(0 if (3,10)<=sys.version_info[:2]<=(3,13) else 1)" >nul 2>nul && set "PY=py -3"
if defined PY exit /b 0
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
    if not defined PY (
        "%%D\python.exe" -c "import venv,ssl,encodings,sys;sys.exit(0 if (3,10)<=sys.version_info[:2]<=(3,13) else 1)" >nul 2>nul && set PY="%%D\python.exe"
    )
)
exit /b 0

:nopython
echo.
echo [ERROR] No working Python could be found or installed.
echo Please install Python 3.12 from https://www.python.org/downloads/
echo Tick "Add python.exe to PATH", then double-click run.bat again.
start "" https://www.python.org/downloads/
pause
exit /b 1

:havepython

REM ---------- 2. Virtual environment ----------
REM Remove a broken .venv left over from a failed earlier attempt
if exist ".venv" (
    if not exist ".venv\Scripts\python.exe" (
        rmdir /s /q ".venv"
    ) else (
        ".venv\Scripts\python.exe" -c "import sys" >nul 2>nul
        if errorlevel 1 rmdir /s /q ".venv"
    )
)

if not exist ".venv\Scripts\python.exe" (
    echo [1/5] Creating virtual environment...
    %PY% -m venv .venv >nul 2>nul
)

if exist ".venv\Scripts\python.exe" (
    set RUNPY=".venv\Scripts\python.exe"
    set "PIPFLAGS="
    echo Using virtual environment.
) else (
    echo Virtual environment could not be created - using system Python instead.
    set RUNPY=%PY%
    set "PIPFLAGS=--user"
)

REM ---------- 3. Dependencies ----------
set "MARK=.deps_v2"
if not exist "%MARK%" (
    echo [2/5] Installing dependencies - about a minute...
    %RUNPY% -m pip install --upgrade pip %PIPFLAGS% >nul 2>nul
    %RUNPY% -m pip install %PIPFLAGS% -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Dependency install failed. Check your internet connection.
        pause
        exit /b 1
    )
    echo done> "%MARK%"
) else (
    echo [2/5] Dependencies already installed.
)

REM ---------- 4. .env ----------
if not exist ".env" (
    copy ".env.example" ".env" >nul
    echo [3/5] Created .env
) else (
    echo [3/5] .env found.
)

REM ---------- 4b. Free Pollinations key for images (asked once) ----------
findstr /b /c:"STORYFORGE_POLLINATIONS_KEY" ".env" >nul 2>nul
if errorlevel 1 (
    echo.
    echo Pictures work best with a FREE Pollinations key - the no-key mode often fails.
    echo Get one in about a minute: open https://enter.pollinations.ai , sign in,
    echo create a key, and copy it.
    set "PKEY="
    set /p PKEY="Paste your key here, or just press Enter to skip: "
    >>".env" echo.
    >>".env" echo STORYFORGE_POLLINATIONS_KEY=!PKEY!
    echo.
)

REM ---------- 5. Ollama (install if missing) ----------
set "MODEL=qwen2.5:7b-instruct"
if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" set "PATH=%LOCALAPPDATA%\Programs\Ollama;!PATH!"

where ollama >nul 2>nul
if errorlevel 1 (
    echo Ollama not found. Installing automatically...
    where winget >nul 2>nul
    if not errorlevel 1 (
        winget install -e --id Ollama.Ollama --silent --accept-package-agreements --accept-source-agreements
    )
    if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" set "PATH=%LOCALAPPDATA%\Programs\Ollama;!PATH!"
)
where ollama >nul 2>nul
if errorlevel 1 (
    echo.
    echo [ERROR] Could not install Ollama automatically.
    echo Install it from https://ollama.com/download then run this file again.
    start "" https://ollama.com/download
    pause
    exit /b 1
)

curl -s http://localhost:11434 >nul 2>nul
if errorlevel 1 (
    echo [4/5] Starting Ollama...
    start "Ollama" /min ollama serve
    timeout /t 6 /nobreak >nul
) else (
    echo [4/5] Ollama is running.
)

ollama list | findstr /i /c:"%MODEL%" >nul 2>nul
if errorlevel 1 (
    echo Downloading story model %MODEL% - first time only, about 4.7 GB...
    ollama pull %MODEL%
    if errorlevel 1 (
        echo [ERROR] Model download failed. Check your internet connection.
        pause
        exit /b 1
    )
) else (
    echo Model %MODEL% already downloaded.
)

REM ---------- 6. Launch app + open browser ----------
if not defined STORYFORGE_LLM_TIMEOUT set "STORYFORGE_LLM_TIMEOUT=1800"
echo [5/5] Starting StoryForge at http://localhost:8000
echo Keep this window open. Close it to stop the app.
echo.
start "" cmd /c "timeout /t 4 /nobreak >nul & start http://localhost:8000"
%RUNPY% run.py

echo.
echo StoryForge stopped.
pause
