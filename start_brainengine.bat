@echo off
setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] .venv\Scripts\python.exe was not found.
    echo Place this batch file in the Step-driven MultiBrainEngine project folder.
    pause
    exit /b 1
)

echo Starting Step-driven MultiBrainEngine...
".venv\Scripts\python.exe" "engine\start_web_ui.py"

if errorlevel 1 (
    echo.
    echo Step-driven MultiBrainEngine stopped with an error.
    pause
)

endlocal
