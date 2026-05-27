#!/bin/bash
set -e

echo "=== Installation de LBC DealFinder Hub ==="
echo

if ! command -v python3 &> /dev/null; then
    echo "[ERREUR] python3 non trouvé. Installe Python 3.11+ depuis https://python.org/downloads"
    exit 1
fi

echo "[1/2] Installation des dépendances Python..."
pip3 install -r requirements.txt

echo "[2/2] Installation de Chromium pour Playwright..."
playwright install chromium

echo
echo "=== Installation terminée ! ==="
echo
echo "Pour lancer : python3 server.py"
echo "Puis ouvre Chrome / Edge sur : https://shisuboi.github.io/lbc-hub"
