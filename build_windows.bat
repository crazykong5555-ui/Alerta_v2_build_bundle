\
:: build_windows.bat
:: Usage: open an Administrator Powershell/CMD, create a venv, install requirements and pyinstaller, then run this script.
:: Example (PowerShell):
:: python -m venv venv
:: .\venv\Scripts\Activate.ps1
:: pip install -r requirements.txt pyinstaller
:: .\build_windows.bat

:: Create single-file exe (console window will appear). To hide console, use --noconsole
pyinstaller --onefile --name alerta_v2 alerta_v2.py

:: If you want to hide the console window (GUI app), use:
:: pyinstaller --onefile --noconsole --name alerta_v2 alerta_v2.py

:: The resulting .exe will be in the "dist" folder.
pause
