# Pipeline automatisé de détection d'opportunités de revente — Design

- **Date** : 2026-05-29
- **Projet** : LBC DealFinder Hub (`lbc-hub`)
- **Statut** : Spec validée (brainstorming terminé, prête pour les plans d'implémentation par phase)
- **Auteur** : Claude (décisions techniques) + Tristan (produit/UX)

---

## 1. Vision produit

Transformer le hub d'un outil de **scraping manuel + analyse Claude.ai** en un **système autonome de détection d'opportunités de revente** sur Leboncoin : acheter des objets sous-cotés pour les revendre plus cher.

- **La vitesse est critique** : détecter une nouvelle annonce en **moins de 20-30 min** après publication.
- **L'utilisateur est souvent absent** : il doit pouvoir réagir **immédiatement depuis son téléphone** (iPhone surtout).
- **Un seul PC fixe Windows 11** tourne 24/7 et fait tout le travail lourd.
- **100 % gratuit** : aucune clé API payante ; on s'appuie sur les **forfaits API gratuits** + une architecture qui les respecte.

---

## 2. Contraintes & paramètres validés (entrées de conception)

| Paramètre | Décision | Conséquence |
|---|---|---|
| **Budget IA** | 100 % gratuit | APIs gratuites (Gemini/Groq), **pas** d'abonnements chat (pas d'API) |
| **Échelle** | Large : 10+ amis, 30+ recherches | ~500-1500 annonces neuves/jour potentielles → batch + pré-filtre **obligatoires** |
| **Parc mobile** | Surtout iPhone | **Telegram** comme canal d'alerte principal (pas de push web iOS en v1) |
| **GPU du PC** | Bureautique / carte intégrée | **Pas de modèle local** ; plafond dur ≈ 1 000-2 000 appels IA/jour |
| **Périmètre** | Les 12 features conçues d'un bloc | Design complet ; **implémentation séquencée** en 6 phases testables |

### Réalité des forfaits API gratuits (vérifiée mai 2026)

| Fournisseur / modèle | Limite gratuite | Reset | Notes |
|---|---|---|---|
| **Gemini 2.5 Flash-Lite** | ~15 RPM, **1 000 req/jour** | minuit Pacifique | Meilleur cheval de trait gratuit ; gère la vision |
| **Gemini 2.5 Flash** | ~10 RPM, 250 req/jour | minuit Pacifique | Pour l'analyse approfondie |
| **Gemini 2.5 Pro** | ❌ derrière paywall (avril 2026) | — | Indisponible en gratuit |
| **Groq (Llama)** | 30 RPM, ~1 000 req/jour | quotidien | Très rapide ; en réserve / répartition |

⚠️ **Piège** : chez Gemini les quotas sont **par projet/compte, pas par clé** — multiplier les clés n'augmente pas le quota (et Google a baissé le gratuit de 50-80 % en déc. 2025). On combine des **fournisseurs distincts**, pas des clés.

**Conclusion de faisabilité** : le 100 % gratuit tient à grande échelle **grâce à** (1) un pré-filtre par règles sans IA, (2) le **triage groupé** (10-20 annonces/requête → ÷10-20 d'appels), (3) l'analyse coûteuse réservée aux urgentes, (4) un routeur multi-fournisseurs. 1 000 req/jour batchées ≈ **10 000-20 000 annonces/jour** analysables.

---

## 3. Le pivot architectural central

> **Invariant cassé (délibérément)** : jusqu'ici « `server.py` ne touche JAMAIS Supabase ; seul le navigateur publie via JWT membre ». Un pipeline 24/7 **sans personne au clavier** impose que le **PC écrive lui-même dans Supabase** et **appelle l'IA lui-même**. `server.py` passe d'« outil de scrape à la demande » à **« démon autonome »**.

À mettre à jour dans `CLAUDE.md` lors de l'implémentation.

### Vue d'ensemble du flux

```
                          ┌──────────────────────────────────────────────┐
                          │   PC FIXE WINDOWS 11 (24/7) — « le cerveau »  │
  Leboncoin ◀─Playwright──┤  server.py --auto (1 seul Chromium partagé)   │
  (scrape)                │   ├─ API HTTP :8080  (existant, INTACT)       │
                          │   ├─ MOTEUR AUTONOME (nouveau)                │
  APIs IA gratuites ◀─────┤   │    scheduler→scrape→dédup→IA cascade      │
  (Gemini / Groq)         │   ├─ SQLite local (cerveau: vu / prix / marché)│
                          │   └─ Bot Telegram (push sortant)              │
                          └────────────────┬─────────────────────────────┘
                                           │ écrit via service_role (REST PostgREST)
                                           ▼
                          ┌─────────────────────────────┐
                          │  SUPABASE (couche partagée)  │
   iPhone ◀──Telegram─────┤  opportunities, watchlists,  │
                          │  journal, coordination...    │
                          └────────────────┬────────────┘
                                           ▲ SDK JS + JWT membre + RLS (inchangé)
                          ┌────────────────┴────────────┐
                          │  HUB (GitHub Pages, SPA)     │
                          │  feed + 3 onglets            │
                          └──────────────────────────────┘
```

### Découplage mobile (crucial)

Le pipeline auto **ne touche jamais `localhost:8080`** : tout passe par **Supabase + Telegram**. Donc **tout fonctionne sur iPhone** (feed, journal, alertes) sans accès au PC. `localhost:8080` ne sert plus que pour le **scraper manuel legacy** (sur le PC).

---

## 4. Le démon autonome (`server.py --auto`)

- **Même process, un seul Chromium partagé.** Plusieurs navigateurs = plusieurs empreintes = plus de blocages Datadome. Le moteur réutilise `ensure_browser()` et un **verrou unique de scrape** : scrape manuel et scrape auto **ne naviguent jamais en même temps**.
- **Moteur = boucle de fond `asyncio`** démarrée au boot via le flag `--auto`. L'API HTTP actuelle (scrape manuel, SSE, import JSON) **reste intacte**.
- **Write-path Supabase** : clé **`service_role`** dans un `.env` local (jamais committée, `.gitignore`), appels **REST PostgREST via `aiohttp`** (déjà présent, pas de SDK lourd). Le frontend, lui, ne change pas (anon key + JWT + RLS).
- Deux chemins d'écriture : **moteur** (confiance, service_role) et **membres** (RLS).

---

## 5. Moteur de scrape 24/7

### 5.1 Stratégie de scrape (inversion vs aujourd'hui)

- **Scrape de la page de résultats uniquement** (triée par date) : elle contient déjà `id, titre, prix, ville, miniature, URL`. Suffisant pour détecter le neuf.
- **Sortie anticipée** : dès qu'on rencontre une annonce **déjà vue**, on arrête de scanner la page (liste triée par date → on ne lit que le delta).
- **Page détail ouverte uniquement** pour les annonces **neuves qui passent le pré-filtre** et nécessitent la description complète. → beaucoup moins de navigations.

### 5.2 Ordonnancement

- File **round-robin** des recherches actives, scrapes en série (un seul Chromium).
- Estimation : ~15-20 s/recherche en mode résultats-only → **30 recherches ≈ 8-10 min/cycle** (< cible 20-30 min).
- Le PC **tire la liste des recherches actives depuis Supabase** (`watchlist_searches`) toutes les quelques minutes et **fusionne les doublons** (même recherche chez 2 membres = scrapée 1 fois).
- Si volume élevé (60+), priorisation par score/urgence/fraîcheur.

### 5.3 Anti-Datadome sans humain (décision : **gratuit + alerte manuelle**)

- **Réduire les blocages** : profil de navigateur **persistant** (`launch_persistent_context` → conserve le cookie de clairance Datadome entre redémarrages), scrape résultats-only, **pacing aléatoire** (jitter), **non-headless** (moins détectable + permet la résolution manuelle).
- **Quand ça bloque** : back-off exponentiel **+ alerte Telegram** à Tristan (« viens résoudre le captcha »). Réutilise le mécanisme `captcha_event` existant.
- **Limite assumée** : la cible « < 30 min » tient tant qu'on n'est pas bloqué ; un blocage en l'absence de Tristan crée un trou jusqu'à résolution. Risque connexe : IP maison flaggée à terme (atténué par le pacing).
- **Levier optionnel (phase F)** : branchement vers un solveur captcha payant (2captcha/CapSolver), désactivé par défaut.

### 5.4 Déduplication & historique de prix

- **Clé = ID d'annonce LBC** (numérique, stable, extrait de l'URL).
- État dans **SQLite local** (cf. §8) : `seen_ads` (neuf vs vu), `price_observations` (append **si le prix change**), **baisse de prix → re-déclenche** analyse/alerte.
- `market_observations` : **byproduct gratuit** — chaque annonce scrapée (même rejetée) = un point de prix marché alimentant l'estimation de marge **et** la feature « stats marché » (#12).

---

## 6. Pipeline IA — la cascade de coût

4 étages, du moins cher au plus cher ; chaque étage ne laisse passer qu'une fraction.

| Étage | Quoi | Modèle | Volume |
|---|---|---|---|
| **0 — Pré-filtre règles** | dédup + prix dans fourchette + mots-clés inclus/exclus (blacklist « pour pièces / HS ») + rayon géo. **Zéro IA.** | — | tue le gros du flux |
| **1 — Triage groupé** | 10-20 annonces/requête (titre+prix+ville+extrait) → catégorie 🔴/🟡/⚫, score 0-100, raison courte, drapeau « creuser ? » | Gemini Flash-Lite / Groq | l'essentiel |
| **2 — Analyse approfondie** | 1 appel/annonce : score affiné, **prix marché estimé**, **marge € + %**, **prix max d'achat**, **détection de lot** (prix unitaire, rentable à casser ?), signaux d'opportunité | Gemini Flash / Flash-Lite | 🔴 + 🟡 limites |
| **3 — Analyse photo (vision)** | image téléchargée sur le PC → état réel, incohérences, signaux d'arnaque | Gemini Flash-Lite (vision) | **🔴 uniquement** |

### 6.1 Prix marché réel (grounding)

On **ne demande pas** à l'IA de connaître les prix de tête. On la **nourrit** de comps réels :
- **Primaire** : base `market_observations` locale (gratuite ; chauffe en quelques jours ; cold-start = marges approximatives au début).
- **Secondaire** : scrape de comparaison ciblé (chercher le modèle exact) **uniquement** pour les 🔴 de valeur.

### 6.2 Routeur multi-fournisseurs (`LLMRouter`)

- Connaît les limites de chaque API (RPD/RPM + heure de reset), **compte l'usage du jour** (table SQLite `llm_usage`), route le triage vers le moins cher dispo, **bascule** quand un fournisseur est épuisé.
- v1 : Gemini + Groq. Extensible (OpenRouter/Cerebras gratuits en réserve). Interface `LLMProvider` (même philosophie que `PlatformScraper`).

### 6.3 Définition de l'urgence & seuils (validé)

- **🔴 URGENTE = score élevé + grosse marge** → déclenche un push Telegram. **La distance ne bloque pas** l'urgence (elle sert juste au tri/surbrillance).
- 🟡 Intéressante / ⚫ Passable : visibles dans le hub, **sans push**.
- **Seuil de rentabilité = hybride € ET %** (une affaire compte si elle dépasse à la fois un plancher € et un %), **réglable par recherche**. Sert au calcul du prix max d'achat.

### 6.4 Priorité géographique

- Chaque membre configure sa ville/CP → géocodage via une **table open-data française embarquée localement** (~36 000 communes, minuscule, **aucune API**).
- Proximité = **score par membre** (l'opportunité est partagée, mais « à 5 km » pour l'un, « à 200 km » pour l'autre) : tri/surbrillance dans le feed.

---

## 7. Notifications & coordination contact vendeur

### 7.1 Notifications = bot Telegram (canal principal)

- **Setup** : bot créé via @BotFather, token dans le `.env` du PC.
- **Liaison membre** : bouton « Connecter Telegram » dans le hub → lien `t.me/<bot>?start=<jeton_membre>` → le PC relie automatiquement le `chat_id` au compte (`member_settings.telegram_chat_id`).
- **Déclencheurs** :
  - Opportunité **🔴** → message aux membres abonnés : titre, prix, **marge estimée**, **prix max d'achat**, distance (par membre), miniature + boutons **« 🔗 Voir sur LBC »** et **« ✋ Je contacte »**.
  - Trade passé à **Acheté** → membres qui suivaient l'annonce (favori) reçoivent « @X l'a achetée ».
- Push web (PWA iOS) = **hors v1**, levier optionnel phase F.

### 7.2 Contact vendeur (validé : message natif LBC)

- **LBC pré-remplit déjà** son message par défaut (« est-ce toujours disponible ? ») dans sa zone de contact. → **on ne génère aucun message** : le bouton « Je contacte » **ouvre simplement l'annonce LBC**, LBC fait le reste.

### 7.3 Coordination (validé : aucun blocage, signal informatif)

- **Pas de verrou, pas de timeout.** On ne peut **pas** détecter qu'un message a réellement été envoyé sur LBC (externe). On détecte **uniquement le clic** sur « Je contacte » (hub ou bouton Telegram).
- Affichage **temps réel** (Supabase Realtime + fil Telegram) : « 👀 @X, @Y ont cliqué Je contacte ». Les membres **se coordonnent entre eux** (groupe d'amis).
- Table `contact_coordination` = simple **journal d'intérêt** (qui a cliqué, quand), pas de machine à états.

---

## 8. Modèle de données & volumétrie

**Principe** : séparer le **lourd/privé (local SQLite)** du **léger/partagé (Supabase)**.

### 8.1 SQLite local (PC) — « le cerveau »

```
seen_ads(ad_id PK, first_seen_at, last_seen_at, last_price, status)
price_observations(ad_id, price, observed_at)         -- append si le prix change
market_observations(categorie, prix, ville, observed_at)
llm_usage(provider, day, request_count, token_count)  -- pour le routeur
scrape_log(search_id, last_run_at, status, blocked_count)
outbox(payload, created_at, retries)                  -- writes Supabase en attente (résilience)
```

→ Des milliers d'écritures/jour, **gratuites, rapides, jamais envoyées brutes**. C'est ce qui garde Supabase minuscule. **L'historique de prix reste local.**

### 8.2 Supabase — couche partagée curatée

```sql
-- Nouvelle table principale (séparée du flux manuel legacy searches/listings)
opportunities(
  id uuid pk, ad_id text, source_search_id uuid, platform text,
  title text, price float, url text, image_url text,
  location_city text, location_postal text, lat float, lon float,
  category text check (category in ('urgent','interesting','passable')),
  resale_score float, est_market_price float,
  est_margin_eur float, est_margin_pct float, max_buy_price float,
  is_lot bool, lot_unit_price float, lot_notes text,
  signals jsonb, explanation text, photo_verdict text,
  price_dropped bool, previous_price float,
  model_used text, status text default 'active',
  first_seen_at timestamptz, scraped_at timestamptz, created_at timestamptz default now()
)

watchlist_searches(
  id uuid pk, owner_id uuid, title text, criteria text, source_url text,
  platform text, geo_postal text, geo_radius_km int,
  min_margin_eur float, min_margin_pct float, active bool default true,
  created_at timestamptz default now()
)
-- Toutes les opportunités sont partagées au groupe (validé).

member_settings(
  member_id uuid pk, home_postal text, home_lat float, home_lon float,
  telegram_chat_id text, notify_urgent bool default true, created_at timestamptz
)

contact_coordination(           -- journal d'intérêt, PAS de verrou
  opportunity_id uuid, member_id uuid, clicked_at timestamptz,
  primary key (opportunity_id, member_id)
)

trades(                          -- journal de trading, gardé pour toujours
  id uuid pk, member_id uuid, opportunity_id uuid null,
  title text, status text check (status in ('contacted','bought','sold')),
  buy_price float, sell_price float, margin_eur float,
  contacted_at timestamptz, bought_at timestamptz, sold_at timestamptz,
  created_at timestamptz default now()
)

market_stats(                    -- agrégats poussés périodiquement par le PC
  categorie text, median_price float, sample_size int,
  trend text, updated_at timestamptz, primary key (categorie)
)
```

`profiles` / `favorites` restent. Les tables legacy `searches` / `listings` (workflow manuel Claude.ai) **restent intactes**.

### 8.3 Volumétrie & garde-fous (free tier 500 Mo)

- Opportunités curatées ≈ 150-600/jour × ~1,5 Ko ≈ **~1 Mo/jour** → ~30 Mo en régime permanent (rétention 30 j).
- **Rétention** : opportunités **purgées après 30 jours** (sauf si liées à un trade/favori) ; **journal & favoris gardés pour toujours**.
- **Photos JAMAIS stockées** : octets envoyés à l'API vision, on garde le **verdict texte** ; miniature du feed **hot-linkée depuis le CDN LBC** (zéro stockage/bande passante).
- **Passe de maintenance quotidienne** (PC) : purge 30 j, recalcul `market_stats`, flush outbox.
- **RLS** : lecture des `opportunities` / `watchlist_searches` / `trades` / `market_stats` ouverte aux membres authentifiés ; écritures membres scopées par `auth.uid()` ; écritures moteur via service_role.

---

## 9. Features membres & les 3 onglets

| Feature | Conception |
|---|---|
| **#7 Watchlists** | Membre crée ses recherches (`watchlist_searches`) ; PC tire + dédup ; **tout partagé au groupe** |
| **#8 Journal** | Contacté → Acheté (prix payé) → Revendu (prix de revente) ; marge réalisée + **bilan global** (`trades`) |
| **#9 Relance 24h** | Branchée sur le **journal** : « Contacté » non avancé après 24h → nudge Telegram |
| **#10 Rapport hebdo** | PC génère (maintenance hebdo) : opportunités manquées, marge totale, catégories rentables → **Telegram + hub** |
| **#11 Tendances** | Dashboards depuis `trades` (ce que le groupe revend le mieux) |
| **#12 Stats marché** | Depuis `market_stats` (byproduct, quasi gratuit) |

**Information architecture — 3 onglets** (rangement affiné à l'implémentation via le **taste-skill** ; le polish visuel n'est pas figé ici) :

| Onglet | Contenu |
|---|---|
| **① Opportunités** | feed live 🔴/🟡/⚫, tri score/urgence, surbrillance proximité, filtres (catégorie, plateforme, recherche, baisse de prix), détail + « Je contacte » + intérêts + « ajouter au journal » |
| **② Mon espace** | mes recherches, mon journal, favoris/suivis, connexion Telegram & prefs notif |
| **③ Tendances** | bilan du groupe (classement marges), catégories rentables, stats marché, dernier rapport hebdo |

Routes legacy (`/scraper`, `/search/:id`) **intactes**.

---

## 10. Déploiement, résilience & monitoring

### 10.1 Démarrage 24/7 (Windows)

- Chromium **visible** (non-headless) requis pour la résolution manuelle des captchas → **service Windows session 0 exclu**.
- **Auto-login du compte habituel** (validé) + tâche **Planificateur de tâches** à l'ouverture de session → `start-agent.bat` (`python server.py --auto`).
- Le `.bat` **relance** si le process meurt + « redémarrer en cas d'échec » du Planificateur. **Pas de Docker.**
- **Recommandé** : BitLocker (disque chiffré → PC volé éteint = illisible).

### 10.2 Résilience

- Boucle en `try/except` : un crash sur une recherche **n'arrête pas** le moteur.
- **Outbox local** : Supabase/Internet down → opportunités bufferisées (SQLite `outbox`) et **rejouées** au retour.
- Quotas IA épuisés → bascule de fournisseur ; si tout épuisé → **prioriser les 🔴** et reporter le reste au reset. **Dégradation gracieuse.**
- SQLite + profil navigateur persistant → **reprise** après redémarrage (vu + cookie Datadome conservés).

### 10.3 Monitoring

- Endpoint `/api/agent-status` (boucle vivante, dernier cycle, blocages, quotas, file).
- **Heartbeat Telegram** quotidien (« PC vivant + stats du jour ») **+ alerte** si moteur bloqué/down > 15 min.

---

## 11. Roadmap d'implémentation

Tout est conçu d'un bloc ; on **construit dans cet ordre**, chaque phase testée avant la suivante. **Chaque phase aura son propre plan détaillé** (spec → plan → implémentation).

| Phase | Livrable | Validation |
|---|---|---|
| **A — Fondation moteur** | `--auto`, scrape results-only, cerveau SQLite, dédup, baisse de prix, scheduler, pull watchlist, write-path Supabase. **Sans IA** (opportunités brutes). + autostart | Moteur 24/7 stable |
| **B — Pipeline IA** | pré-filtre, `LLMRouter` (Gemini+Groq), triage batch, analyse approfondie, photo, grounding marché, scoring/marge/prix max/lot/signaux | Coût = 0 + qualité du tri |
| **C — Hub Opportunités + Telegram** | onglet ①, détail, « Je contacte » + intérêts Realtime, bot Telegram + liaison + push 🔴 | **= MVP complet (détecter + réagir mobile)** |
| **D — Mon espace** | config watchlists, journal + marges + bilan, favoris, prefs notif, relance 24h | Couche perso |
| **E — Tendances** | dashboards groupe, stats marché, rapport hebdo, classement | S'appuie sur A-D |
| **F — Durcissement** | monitoring/heartbeat, purge auto 30 j, leviers optionnels (solveur payant, providers IA en réserve, push web iOS) | Robustesse |

---

## 12. Journal des décisions

| # | Décision | Choix |
|---|---|---|
| P-01 | Budget IA | 100 % gratuit via APIs gratuites (Gemini+Groq), jamais via abonnements chat |
| P-02 | Échelle | Large (10+ amis, 30+ recherches) → batch + pré-filtre obligatoires |
| P-03 | Notifications | Telegram (canal principal) ; push web iOS hors v1 |
| P-04 | Modèle local | Aucun (PC bureautique) |
| P-05 | Write-path Supabase | `service_role` en `.env` local, REST via aiohttp |
| P-06 | Anti-Datadome | Gratuit + alerte Telegram manuelle (stealth + back-off) |
| P-07 | Définition 🔴 | Score élevé + grosse marge (distance non bloquante) |
| P-08 | Seuil rentabilité | Hybride € ET %, réglable par recherche |
| P-09 | Rétention opportunités | 30 jours (journal/favoris pour toujours) |
| P-10 | Message contact | Natif LBC (pas de génération IA) |
| P-11 | Coordination | Aucun verrou ; journal d'intérêt informatif (clic uniquement) |
| P-12 | Onglets | 3 (Opportunités / Mon espace / Tendances), rangement affiné via taste-skill |
| P-13 | Visibilité recherches | Tout partagé au groupe |
| P-14 | Auto-login Windows | Compte habituel + Task Scheduler ; BitLocker recommandé |

---

## 13. Risques & limites assumés

- **Trous de détection Datadome** : si blocage en l'absence de Tristan, scrape en pause jusqu'à résolution manuelle. La cible « < 30 min » est conditionnelle.
- **IP maison flaggée** à terme (atténué par pacing ; pas de proxy en v1).
- **Cold-start prix marché** : marges approximatives les premiers jours (base `market_observations` vide).
- **Quotas gratuits dégressifs** : Google a déjà coupé 50-80 % en déc. 2025 ; le routeur multi-fournisseurs + le batch protègent, mais une nouvelle coupe imposerait d'ajouter des fournisseurs (OpenRouter/Cerebras) ou d'accepter un petit budget.
- **CGU LBC** : scraping automatisé en zone grise ; risque inhérent assumé pour un usage privé.
- **Sécurité service_role** : clé « dieu » sur le PC ; mitigée par `.gitignore` + BitLocker ; révocable si fuite.

---

## 14. Prochaine étape

Rédiger le **plan d'implémentation de la Phase A** (Fondation moteur) via la skill `writing-plans`. Les phases B→F suivront, chacune avec son propre plan.
