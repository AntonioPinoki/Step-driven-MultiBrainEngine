@echo off
setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] .venv\Scripts\python.exe was not found.
    echo Place this batch file in the MultiAgent-BrainEngine-SillyTavern folder.
    echo Expected location: H:\AI\MultiAgent-BrainEngine-SillyTavern
    pause
    exit /b 1
)

echo Starting MultiAgent BrainEngine...
".venv\Scripts\python.exe" "engine\start_web_ui.py"

if errorlevel 1 (
    echo.
    echo BrainEngine stopped with an error.
    pause
)

endlocal
