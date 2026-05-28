# Reprise sur PC fixe — où on en est

> Document de continuité créé depuis le laptop le 2026-05-28.
> Sur le laptop il manquait les pré-requis pour exécuter le scraping E2E
> (server.py local + chromium configuré + accès au workflow Claude.ai),
> donc on a stoppé là et tout consigné ici.

---

## TL;DR — quoi faire dans l'ordre

1. **Pré-flight rapide** (sync code + relancer server.py + check pytest) — § 1 ci-dessous
2. **Appliquer les migrations Supabase** → cf. [supabase/SECTION-1-A-FAIRE.md](supabase/SECTION-1-A-FAIRE.md)
3. **Smoke-tester la mini-fix admin** (colonne "Expire" sur `/admin`) — § 2 ci-dessous
4. **Dérouler les Sections 3 → 8** de [TESTING-phase2-3.md](TESTING-phase2-3.md)
5. Si tout passe → tag `v1.6.1` ou `v1.6.0-tested`. Sinon → débugger avec les pièges connus du [CLAUDE.md](CLAUDE.md) § "Bugs / pièges connus"

---

## État au moment de la pause

| Item | Statut |
|---|---|
| Branche | `master` |
| Dernier commit | `23527e4` — *feat(admin): show invitation expiry date in existing-invitations table* |
| Tag courant | `v1.6.0-phase3` (pas encore re-taggé pour la fix admin) |
| Tests pytest | ✅ 3/3 passent |
| Déploiement prod | ✅ Push effectué à 2026-05-28 12:25, GH Actions auto-déploie |
| Migrations Supabase 1.2 + 1.3 | ❌ **PAS encore appliquées** — bloque les Sections 6 et 8 |
| Sites URL Supabase Auth | ❓ à vérifier (cf. § 1.4 de SECTION-1-A-FAIRE.md) |

### Sections de TESTING-phase2-3.md déjà validées

- **Section 2 (Admin UI / v1.1.0-admin)** : ✅ validée depuis le laptop
  - Lien "🛠️ Admin" visible pour admin uniquement
  - Page `/admin` s'affiche avec les 2 cartes (Inviter, Invitations existantes)
  - Génération d'invitation → URL copiable + bouton "✅ Copié !" OK
  - Tableau refresh auto après création
  - **Amélioration ajoutée pendant les tests** : colonne "Expire" dans le tableau (commit `23527e4`)
  - ⚠️ Au moment de la pause, la colonne "Expire" n'apparaissait pas encore sur prod (déploiement en cours / cache CDN). À re-vérifier après le pull + Ctrl+F5 sur PC fixe (cf. § 2 ci-dessous).

### Sections encore à faire

| Section | Sujet | Dépend de Supabase ? |
|---|---|---|
| 3 | Scraper sans Ollama (D-01) | non — mais nécessite `server.py` local + Chromium + accès claude.ai |
| 4 | Hub tri + filtres | non |
| 5 | Pages profil | non |
| 6 | Favoris | ✅ migration 1.2 |
| 7 | Notifications | non |
| 8 | Annonces expirées | ✅ migration 1.3 |

Ordre conseillé sur PC fixe : appliquer Supabase d'abord (1.2 + 1.3 + check 1.4), puis enchaîner 3 → 8 dans l'ordre.

---

## 1. Pré-flight rapide sur PC fixe

Suppose que tu travailles dans `C:\Users\trist\Documents\lbc\lbc-hub` (= le repo cloné, **pas** son parent).

```powershell
# Sync le code (laptop a pushé le commit 23527e4)
git fetch --tags
git checkout master
git pull --ff-only

# Vérifier qu'on est bien au bon commit
git log --oneline -1
# Attendu : 23527e4 feat(admin): show invitation expiry date in existing-invitations table

# Tests backend toujours verts
python -m pytest tests/ -q
# Attendu : 3 passed

# Relancer le serveur local en arrière-plan (pour Section 3 surtout)
Start-Process python -ArgumentList "server.py" -WindowStyle Hidden `
  -RedirectStandardOutput "server.out.log" -RedirectStandardError "server.err.log"

# Vérification
Start-Sleep 2
Invoke-WebRequest -Uri "http://localhost:8080/api/ping" -UseBasicParsing | Select-Object -ExpandProperty Content
# Attendu : {"status": "ok"}
```

Si `playwright install chromium` n'a jamais été fait sur le PC fixe, lancer une fois :

```powershell
playwright install chromium
```

---

## 2. Smoke test : la colonne "Expire" sur /admin

C'est la mini-fix qu'on a livrée depuis le laptop. À valider avant tout :

1. Ouvre **Edge** (rappel : Tracking Prevention de Firefox/Zen casse Supabase) sur :
   👉 https://shisuboi.github.io/lbc-hub/admin
2. Logue-toi en admin (`tristanfranceschetti@gmail.com`)
3. **Ctrl + F5** (hard refresh — ignore le cache GitHub Pages)

À cocher :
- [ ] Le tableau "📜 Invitations existantes" a maintenant **4 colonnes** : `Token` · `Créée` · `Expire` · `Statut`
- [ ] Pour les invitations actives, la date "Expire" est à **J+7** après la date "Créée"
- [ ] Pour les invitations utilisées : la colonne "Expire" affiche aussi la date (peu importe — la donnée est juste là pour info)

Si la colonne **n'apparaît toujours pas** après Ctrl+F5 :
- Vérifie l'état du déploiement : `gh run list --limit 3 --workflow=deploy.yml`
- S'il est en `completed success`, vide complètement le cache du site (DevTools → Application → Storage → Clear site data) puis recharge
- En dernier recours, ouvre `js/pages/admin.js` ligne ~150-175 et vérifie que `<th>Expire</th>` et `<td>${expiresAt}</td>` sont bien présents en local

---

## 3. Appliquer les migrations Supabase

Voir le fichier dédié : **[supabase/SECTION-1-A-FAIRE.md](supabase/SECTION-1-A-FAIRE.md)**

Résumé express :
- 1.1 — Vérifier que le profil admin existe (insert/update si besoin)
- 1.2 — Créer la table `favorites` + RLS
- 1.3 — Ajouter `listings.expired_at` + index + policy UPDATE
- 1.4 — Vérifier `Site URL` Auth = `https://shisuboi.github.io/lbc-hub` (pour tester en prod) ou `http://localhost:8080` (pour tester en local)

Tout le SQL est prêt à copier-coller dans le SQL Editor du Dashboard.

---

## 4. Dérouler les Sections de TESTING-phase2-3.md

Faire dans l'ordre, **stopper et débugger dès qu'un truc casse**. Les pièges connus
sont dans [CLAUDE.md](CLAUDE.md) § "Bugs / pièges connus".

### Section 3 — Scraper sans Ollama (D-01)

- **Pré-requis** : server.py tourne en local (cf. § 1 ci-dessus)
- **URL** : http://localhost:8080/scraper (obligatoire en local, le scraper a besoin du serveur)
- **Points clés à vérifier** :
  - 3.1 : plus de dropdown Ollama, plus de case "Ré-analyser", bouton "⚡ Lancer le scraping"
  - 3.2 : scrape s'arrête après l'étape scrape (PAS d'analyse IA automatique)
  - 3.3 : workflow Claude.ai (copier prompt → coller dans claude.ai → joindre brut.json → récupérer JSON → sauver en `.json` local)
  - 3.4 : import du JSON + publish sur le hub → carte avec bandeau violet (cloud)
  - 3.5 : F5 sur scrape récent → le panneau "Étape suivante" persiste (SSE replay)

Détails complets : [TESTING-phase2-3.md § 3](TESTING-phase2-3.md#3-test-scraper-sans-ollama--v120-d01)

### Section 4 — Hub tri + filtres (v1.3.0-feed-sort)

- **URL** : https://shisuboi.github.io/lbc-hub/hub (prod) ou http://localhost:8080/hub (local)
- **Pré-requis** : au moins 5-6 recherches publiées + idéalement 2 auteurs et 2 plateformes pour bien tester les filtres
- **Points clés** :
  - 4.1 : toolbar visible (recherche + tri + chips plateforme + chips auteur + chip Favoris + compteur)
  - 4.2 : 4 modes de tri (récentes, meilleures notes, prix asc/desc)
  - 4.3 : chips plateforme et auteur filtrent correctement
  - 4.4 : recherche texte filtre live sur titre + pseudo
  - 4.5 : Realtime + filtres → compteur monte même si la carte est masquée par filtre

### Section 5 — Pages profil (v1.4.0-profiles)

- **URL** : `/profile/tristan` (clic sur l'avatar dans le header → "Mon profil")
- **Points clés** :
  - 5.1-5.2 : page profil avec avatar, badge admin, 4 stats
  - 5.3 : grille des recherches du user
  - 5.4 : `@username` cliquable partout (hub, search detail) → mène au profil
  - 5.5 : `/profile/inconnu` → page "Profil introuvable" propre

### Section 6 — Favoris (v1.5.0-favorites) ⚠️ Migration 1.2 requise

- **URL** : `/hub` + `/search/<id>`
- **Points clés** :
  - 6.1 : étoile ☆ → ⭐ sur les cartes (clic + hover + glow)
  - 6.2 : chip "☆ Favoris" filtre uniquement les favoris
  - 6.3 : persistance après F5 + isolation RLS (autre user ne voit pas tes favoris)
  - 6.4 : étoile aussi sur la page détail, état synchronisé avec hub
  - 6.5 (optionnel destructif) : suppression search → favori cascade-supprimé

### Section 7 — Notifications (v1.6.0-phase3 partie 1)

- **URL** : `/hub` ouvert sur **Edge** (Notification API ok)
- **Points clés** :
  - 7.1 : titre onglet devient "(1) LBC DealFinder Hub" quand carte arrive en background
  - 7.2 : focus sur l'onglet → reset du compteur
  - 7.3 : bouton "🔕 Activer notifications" → permission granted → "🔔 Notifications ON" + vraie notif système quand carte arrive
  - 7.4 (optionnel) : si permission bloquée → bouton "🔕 Notifications bloquées" grisé
  - 7.5 : pas de notif sur ses propres publications (anti-spam volontaire)

### Section 8 — Annonces expirées (v1.6.0-phase3 partie 2) ⚠️ Migration 1.3 requise

- **URL** : `/search/<id>`
- **Points clés** :
  - 8.1 : bouton "🚫 Marquer expirée" en plus de "Voir l'annonce 🔗" sur chaque listing
  - 8.2 : toggle → bandeau rouge + carte grisée + bouton "↩️ Réactiver"
  - 8.3 : persistance après F5 + toggle back fonctionne
  - 8.4 : visibilité cross-user (volontaire, on est entre potes)
  - 8.5 : RLS bloque update pour anon (théorique)

---

## 5. Si tout passe ✅

- Tag : `git tag -a v1.6.1 -m "fix: invitation expiry date in admin table + Phase 2-3 E2E validation complete"`
- Push : `git push --tags`
- Mettre à jour [CLAUDE.md](CLAUDE.md) ligne 103-104 :
  ```
  - Phases 2-3 (v1.1.0 → v1.6.0) : ✅ validées E2E (cf. `TESTING-phase2-3.md`)
  ```
- Discuter idées Phase 4 (auto-détection expirées via HEAD check côté server.py, recherches planifiées, commentaires, modération admin)

## Si ça casse

Première piste à chaque fois : [CLAUDE.md § "Bugs / pièges connus"](CLAUDE.md) lignes 186-192. Les 6 pièges principaux :

1. **`navigator.locks` du SDK Supabase** : déjà mitigé via `lock: noop`
2. **Tracking Prevention Edge/Firefox** : déjà mitigé via SDK self-hébergé
3. **SPA refresh sur `/hub` → 405** : déjà mitigé par catch-all GET dans server.py
4. **`<base href>` dynamique** : `/lbc-hub/` en prod, `/` en dev
5. **Cross-tab `sessionStorage`** : faire le flow invitation dans **un seul** onglet
6. **`onAuthChange` AVANT `renderHeader`** = deadlock SDK. Ordre dans `main.js` : `await renderHeader()` → `initRouter()` → `onAuthChange()`

Aussi : tableau debug § 9 de [TESTING-phase2-3.md](TESTING-phase2-3.md#9-synthèse--debug-rapide-si-bug) avec symptôme → cause → fix.
