@echo off
echo Starting Market Extractor Pipeline...

:: Navigate to the script directory to ensure everything runs perfectly
cd /d "%~dp0"

:: Activate the virtual environment and run the script
call .venv\Scripts\activate.bat
python ai_extractor\extract_prices.py

pause
