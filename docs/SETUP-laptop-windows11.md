# Setup du moteur LBC sur un nouveau laptop Windows 11

Ce guide part d'un Windows 11 vierge et aboutit à un moteur autonome fonctionnel.
Il complète `docs/DEPLOY-agent-windows.md` (autostart 24/7, à lire après).

---

## 1. Pré-requis à installer une seule fois

### 1.1 Git

1. Télécharger l'installeur depuis **https://git-scm.com** → « Download for Windows ».
2. Lancer l'installeur, tout laisser par défaut.
3. Vérifier dans PowerShell :
   ```powershell
   git --version
   # git version 2.xx.x
   ```

### 1.2 Python 3.12 (ou 3.11+)

1. Télécharger depuis **https://www.python.org/downloads/windows/** — choisir la version
   **3.12.x Windows installer (64-bit)**.
2. ⚠️ **Cocher « Add Python to PATH »** avant de cliquer Install.
3. Vérifier dans PowerShell :
   ```powershell
   python --version
   # Python 3.12.x
   pip --version
   # pip 24.x ...
   ```
   > Si `python` n'est pas reconnu, fermer/rouvrir PowerShell.

---

## 2. Cloner le repo

```powershell
# Choisir l'emplacement (ex. Bureau ou Documents)
cd "$env:USERPROFILE\Documents"
git clone https://github.com/Shisuboi/lbc-hub.git lbc
cd lbc
```

---

## 3. Installer les dépendances Python

```powershell
pip install -r requirements.txt
```

Contenu de `requirements.txt` :
```
playwright
aiohttp>=3.10
pytest>=8.0
pytest-asyncio>=0.23
pytest-aiohttp>=1.0
```

---

## 4. Installer Chromium (Playwright)

```powershell
python -m playwright install chromium
```

Cette commande télécharge ~150 Mo. Une seule fois par machine.

---

## 5. Créer le fichier `.env`

Le fichier `.env` contient les clés secrètes — il **n'est pas dans le repo** (gitignore).
Deux options :

### Option A — Copier depuis le PC fixe (recommandé)
Copier le fichier `.env` du PC fixe vers `C:\Users\<toi>\Documents\lbc\.env`.
Via clé USB, OneDrive, ou SSH.

### Option B — Recréer manuellement
```powershell
copy .env.example .env
notepad .env
```
Remplir les valeurs :
- `SUPABASE_SERVICE_KEY` : Supabase Dashboard → Project Settings → API → **service_role** (secret).
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_GROUP_ID`, `TELEGRAM_TRISTAN_ID` : copier depuis le `.env` du PC ou depuis les notes.
- Les variables IA (`GEMINI_API_KEY`, etc.) sont optionnelles — sans elles, le moteur scrape sans enrichissement.

---

## 6. Vérifier que tout fonctionne

### Test 1 — Serveur dev (sans moteur)
```powershell
python server.py
```
Ouvrir http://localhost:8080 dans le navigateur. Le hub doit s'afficher.
`Ctrl+C` pour arrêter.

### Test 2 — Suite de tests backend
```powershell
python -m pytest tests/ -q
# ... 194 passed
```

### Test 3 — Moteur autonome (scrape + IA)
```powershell
python server.py --auto
```
Dans les logs, tu dois voir :
```
🤖 Moteur autonome démarré
🔁 Heartbeat worker démarré
```
Après quelques minutes, les opportunités doivent apparaître dans le feed du hub.

---

## 7. Autostart (moteur 24/7)

Une fois le test 3 validé, configurer le démarrage automatique avec le
Planificateur de tâches Windows → voir **`docs/DEPLOY-agent-windows.md`**.

---

## 8. Résolution de problèmes courants

| Symptôme | Cause probable | Solution |
|---|---|---|
| `python` non reconnu | PATH non ajouté | Réinstaller Python en cochant « Add to PATH » |
| `pip install` échoue sur `playwright` | Version Python < 3.11 | Vérifier `python --version`, mettre à jour |
| Chromium ne se lance pas | Playwright non installé | Relancer `python -m playwright install chromium` |
| Erreur `SUPABASE_URL non défini` | `.env` manquant ou incomplet | Vérifier que le fichier `.env` est dans le dossier `lbc/` |
| Feed vide après `--auto` | Aucune recherche active dans Supabase | Activer une recherche sur `/watchlist` |
| Captcha Datadome | LBC bloque l'IP | Résoudre manuellement dans la fenêtre Chromium qui s'ouvre |

---

## 9. Mise à jour du code

```powershell
cd "$env:USERPROFILE\Documents\lbc"
git pull
pip install -r requirements.txt   # si requirements.txt a changé
```

Les migrations SQL Supabase (`supabase/migrations/`) sont à appliquer **manuellement**
dans le Dashboard Supabase → SQL Editor si elles sont nouvelles depuis la dernière synchro.
