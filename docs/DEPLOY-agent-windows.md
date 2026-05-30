# Déploiement du moteur autonome (Windows 11, 24/7)

## 1. Pré-requis
- Python 3.11 + dépendances : `pip install -r requirements.txt`
- Chromium Playwright : `python -m playwright install chromium`
- Fichier `.env` créé à partir de `.env.example` (avec la clé `service_role`
  copiée depuis Supabase → Project Settings → API → `service_role` secret).

## 2. Test manuel
Double-cliquer `start-agent.bat`. Une fenêtre Chromium doit s'ouvrir et le terminal
afficher « 🤖 Moteur autonome démarré ». Laisser tourner quelques minutes.

## 3. Autostart à l'ouverture de session
1. Activer l'auto-login Windows du compte habituel :
   - `Win+R` → `netplwiz` → décocher « Les utilisateurs doivent entrer un nom… »
     → entrer le mot de passe du compte.
2. Planificateur de tâches → Créer une tâche :
   - Général : « LBC Agent », cocher « Exécuter seulement si l'utilisateur est connecté ».
   - Déclencheurs : « À l'ouverture de session » (utilisateur courant).
   - Actions : Démarrer un programme → `start-agent.bat` (chemin complet),
     « Commencer dans » = dossier du projet.
   - Paramètres : cocher « Redémarrer en cas d'échec » (toutes les 1 min, 3 fois).
3. (Recommandé) Activer **BitLocker** sur le disque système.

## 4. Vérifier
Redémarrer le PC : la session s'ouvre seule, `start-agent.bat` se lance,
Chromium apparaît. En cas de captcha Datadome, résoudre dans la fenêtre Chromium.
