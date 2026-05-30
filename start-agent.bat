@echo off
REM Lanceur du moteur autonome LBC. Relance automatiquement si le process meurt.
cd /d "%~dp0"
:loop
echo [%date% %time%] Demarrage du moteur autonome...
python server.py --auto
echo [%date% %time%] Le process s'est arrete (code %errorlevel%). Relance dans 10s...
timeout /t 10 /nobreak >nul
goto loop
