# Proximité — filtre par rayon sur le feed

> Date : 2026-06-02
> Reprend le besoin « proximité » de la spec d'origine (`2026-05-29-…` §158 : distance = tri/affichage
> par membre, **n'entre pas** dans la note IA), recadré en **filtre par rayon choisi par l'utilisateur**.
> Statut : design validé, à implémenter.

## 1. Objectif

Permettre à chaque membre de **filtrer le feed par distance depuis son domicile** : rayon **5 / 10 /
25 / 50 / 100 km / Toute la France**. La distance sert **uniquement** au filtrage/affichage côté feed
— elle n'entre **pas** dans la note IA ni dans la catégorie (cohérent avec la spec d'origine).

## 2. Le verrou de données

Aujourd'hui le scraper ne capte que le **nom de ville** ; `opportunities.lat/lon` (colonnes déjà
présentes depuis la Phase A) ne sont **jamais remplies**. Il faut donc géocoder.

**Géocodage = API BAN gratuite** (`https://api-adresse.data.gouv.fr/search/?q=<ville>&limit=1`) :
publique, **sans clé, sans crédit, sans quota bloquant**, CORS ouvert. Précision = centre de la
commune → largement suffisant pour des paliers de plusieurs km.

## 3. Architecture

### a) Moteur — remplir `opportunities.lat/lon`
- Nouveau module `engine/geo.py` : `geocode_city(session, city) -> (lat, lon) | None`, appelle la BAN,
  best-effort (réseau KO → `None`).
- **Cache SQLite** (Brain) : table `city_geo(city TEXT PK, lat REAL, lon REAL, geocoded_at INT)` pour ne
  géocoder chaque ville **qu'une fois** (des milliers d'annonces, mais peu de villes distinctes).
  Méthodes `Brain.get_city_geo(city)` / `Brain.set_city_geo(city, lat, lon)`.
- L'opportunité n'est **écrite dans Supabase que par `engine/enrich.py`** (le worker d'enrichissement ;
  sans `GEMINI_API_KEY`, rien n'est écrit → géocodage sans objet). C'est donc **là** qu'on géocode :
  juste avant `supa.insert_opportunity(payload)`, si `payload["location_city"]` est connue, résoudre
  via cache puis BAN et **ajouter `lat`/`lon` au payload**. **Best-effort** : échec → on n'ajoute pas
  les clés (elles restent `null` côté DB), l'opportunité est écrite quand même (jamais bloquant).
- ⚠️ `build_opportunity_payload` (`engine/supa.py`) n'inclut **pas** les clés `lat/lon` aujourd'hui →
  elles valent `null` en base. On les **ajoute** dans le worker, sans changer le schéma Supabase
  (colonnes `lat/lon` déjà présentes depuis la Phase A).

### b) Site — domicile + sélecteur de rayon
- **Domicile** (localStorage, pas de DB) : nouveau lib `js/lib/geo-home.js` :
  - `getHome()` → `{ label, lat, lon } | null` (depuis localStorage clé `lbc-home`).
  - `setHome(query)` → géocode `query` (CP ou ville) via la **même API BAN** (fetch navigateur),
    stocke `{ label, lat, lon }`, renvoie l'objet ; best-effort (échec → message clair).
  - `clearHome()`.
  - `haversineKm(lat1, lon1, lat2, lon2)` → distance en km.
- **`/feed`** (`js/pages/feed.js` + `js/components/opportunity-row.js`) :
  - Toolbar : un champ « 📍 Mon secteur » (saisie CP/ville → `setHome`) + un `<select>` rayon
    (5/10/25/50/100 / « Toute la France »). Le rayon choisi est aussi mémorisé en localStorage.
  - `renderList` : si un domicile est défini ET un rayon ≠ « France », ne garder que les opportunités
    dont `lat/lon` existent ET `haversineKm(home, opp) ≤ rayon`. « Toute la France » = aucun filtre
    distance. Sans domicile défini = aucun filtre (+ invite discrète à le renseigner).
  - Affichage : « 📍 à ~X km » sur la ligne quand domicile défini et `lat/lon` connues.
  - Items **sans `lat/lon`** (géocodage échoué / anciennes lignes) : exclus quand un rayon est actif,
    visibles sous « Toute la France ».

## 4. Hors scope (assumé)
- Pas de `member_settings` ni de domicile synchronisé multi-appareils (localStorage par navigateur,
  comme `comment-seen`). Re-saisir si on change de navigateur.
- Pas de backfill des anciennes `opportunities` sans coords (elles apparaîtront sous « Toute la France »
  et se rempliront si re-vues par le moteur). Un script de backfill ponctuel reste possible plus tard.
- La distance n'influence **pas** la note IA (inchangé).

## 5. Tests
- **pytest** : `engine/geo.py` (géocodage via BAN mocké : succès → (lat,lon), erreur réseau → None) ;
  cache `Brain.get/set_city_geo` ; remplissage `lat/lon` du payload dans le worker (BAN mockée).
- **Frontend** (convention : manuel) : définir un domicile, choisir un rayon → le feed se filtre ;
  « Toute la France » → tout revient ; « à ~X km » cohérent ; console F12 propre.
