@echo off
echo === Installation de LBC DealFinder Hub ===
echo.
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERREUR] Python non trouve. Installe Python 3.11+ depuis https://python.org/downloads
    echo Pense a cocher "Add Python to PATH" pendant l'installation.
    pause
    exit /b 1
)

echo [1/2] Installation des dependances Python...
pip install -r requirements.txt
if errorlevel 1 (
    echo [ERREUR] pip a echoue. Verifie ta connexion internet.
    pause
    exit /b 1
)

echo [2/2] Installation de Chromium pour Playwright...
playwright install chromium
if errorlevel 1 (
    echo [ERREUR] Echec de l'installation de Chromium.
    pause
    exit /b 1
)

echo.
echo === Installation terminee ! ===
echo.
echo Pour lancer le serveur : double-clic sur server.py
echo OU dans un terminal : python server.py
echo.
echo Puis ouvre Chrome / Edge sur : https://shisuboi.github.io/lbc-hub
echo.
pause
