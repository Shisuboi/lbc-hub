# Proximité — filtre par rayon sur le feed — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permettre à chaque membre de filtrer le feed par distance (rayon 5/10/25/50/100 km ou Toute la France) depuis son domicile.

**Architecture:** Le moteur géocode la ville de chaque opportunité via l'API BAN gratuite (cache SQLite local) et remplit `opportunities.lat/lon` au moment de l'écriture (`engine/enrich.py`). Le site stocke le domicile du membre en localStorage (géocodé une fois via BAN), calcule la distance (Haversine) et filtre le feed. Zéro migration (colonnes `lat/lon` déjà présentes).

**Tech Stack:** Python 3.12 (aiohttp, sqlite3, pytest `asyncio_mode=auto`), Vanilla JS ES6, API BAN (`api-adresse.data.gouv.fr`, gratuite, sans clé).

**Spec:** `docs/superpowers/specs/2026-06-02-proximite-rayon-design.md`

**Convention :** pytest = backend uniquement ; frontend = validation manuelle (chargement page + console F12). Le serveur dev = `python server.py`.

---

## File Structure

| Fichier | Action | Responsabilité |
|---|---|---|
| `engine/db.py` | Modify | + table `city_geo` (cache) + `get_city_geo`/`set_city_geo` |
| `engine/geo.py` | Create | `geocode_city` (BAN) + `fill_latlon` (cache→BAN, remplit payload) |
| `engine/enrich.py` | Modify | appelle `fill_latlon` avant l'insertion de l'opportunité |
| `js/lib/opportunities.js` | Modify | ajoute `lat`,`lon` au SELECT |
| `js/lib/geo-home.js` | Create | domicile localStorage + rayon + géocodage BAN + Haversine |
| `js/pages/feed.js` | Modify | toolbar secteur+rayon, filtre distance, passe `distanceKm` |
| `js/components/opportunity-row.js` | Modify | affiche « 📍 à ~X km » |
| `style.css` | Modify | styles secteur/rayon/distance |
| `tests/test_engine_db_citygeo.py` | Create | tests cache city_geo |
| `tests/test_engine_geo.py` | Create | tests geocode_city + fill_latlon |

---

## Task 1 : Cache `city_geo` dans le Brain

**Files:**
- Modify: `engine/db.py` (SCHEMA + 2 méthodes)
- Test: `tests/test_engine_db_citygeo.py`

> Note : `Brain.__init__` exécute `executescript(SCHEMA)` à chaque démarrage ; comme c'est un
> `CREATE TABLE IF NOT EXISTS`, ajouter la table au SCHEMA suffit (créée aussi sur les bases existantes,
> pas d'ALTER nécessaire — contrairement à l'ajout d'une colonne).

- [ ] **Step 1: Écrire les tests**

Create `tests/test_engine_db_citygeo.py`:

```python
from engine.db import Brain


def test_city_geo_absent_returns_none():
    b = Brain(":memory:")
    assert b.get_city_geo("Paris") is None


def test_city_geo_set_then_get():
    b = Brain(":memory:")
    b.set_city_geo("Paris", 48.8566, 2.3522, now=1000)
    assert b.get_city_geo("Paris") == (48.8566, 2.3522)


def test_city_geo_upsert_overwrites():
    b = Brain(":memory:")
    b.set_city_geo("Paris", 1.0, 2.0)
    b.set_city_geo("Paris", 48.8566, 2.3522)
    assert b.get_city_geo("Paris") == (48.8566, 2.3522)
```

- [ ] **Step 2: Lancer → échec**

Run: `python -m pytest tests/test_engine_db_citygeo.py -v`
Expected: FAIL (`AttributeError: 'Brain' object has no attribute 'get_city_geo'`).

- [ ] **Step 3: Ajouter la table au SCHEMA**

Dans `engine/db.py`, ajouter dans la chaîne `SCHEMA` (avant la fermeture `"""`) :

```sql
CREATE TABLE IF NOT EXISTS city_geo (
    city TEXT PRIMARY KEY,
    lat REAL NOT NULL,
    lon REAL NOT NULL,
    geocoded_at INTEGER NOT NULL
);
```

- [ ] **Step 4: Ajouter les méthodes** (dans la classe `Brain`, ex. après `blocked_recent`)

```python
    def get_city_geo(self, city: str):
        """Retourne (lat, lon) en cache pour cette ville, ou None."""
        row = self.conn.execute(
            "SELECT lat, lon FROM city_geo WHERE city = ?", (city,)
        ).fetchone()
        return (row["lat"], row["lon"]) if row else None

    def set_city_geo(self, city: str, lat: float, lon: float, now: int | None = None) -> None:
        now = int(now if now is not None else time.time())
        self.conn.execute(
            "INSERT INTO city_geo (city, lat, lon, geocoded_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(city) DO UPDATE SET lat=excluded.lat, lon=excluded.lon, "
            "geocoded_at=excluded.geocoded_at",
            (city, lat, lon, now),
        )
        self.conn.commit()
```

- [ ] **Step 5: Lancer → succès**

Run: `python -m pytest tests/test_engine_db_citygeo.py tests/test_engine_db.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add engine/db.py tests/test_engine_db_citygeo.py
git commit -m "feat(engine): cache city_geo dans le Brain (proximite)"
```

---

## Task 2 : `engine/geo.py` — géocodage BAN + remplissage

**Files:**
- Create: `engine/geo.py`
- Test: `tests/test_engine_geo.py`

- [ ] **Step 1: Écrire les tests**

Create `tests/test_engine_geo.py`:

```python
import pytest
from aiohttp import web, ClientSession
from engine.db import Brain
from engine.geo import geocode_city, fill_latlon


@pytest.fixture
async def mock_ban(aiohttp_server):
    async def search(request):
        q = (request.query.get("q") or "").lower()
        if "bordeaux" in q:
            return web.json_response({"features": [
                {"geometry": {"coordinates": [-0.5792, 44.8378]},
                 "properties": {"label": "Bordeaux"}}
            ]})
        return web.json_response({"features": []})
    app = web.Application()
    app.router.add_get("/search/", search)
    return await aiohttp_server(app)


async def test_geocode_city_success(mock_ban, monkeypatch):
    monkeypatch.setattr("engine.geo.BAN_URL", str(mock_ban.make_url("/search/")))
    async with ClientSession() as s:
        geo = await geocode_city(s, "Bordeaux")
    assert geo is not None
    lat, lon = geo
    assert round(lat, 2) == 44.84 and round(lon, 2) == -0.58


async def test_geocode_city_unknown_returns_none(mock_ban, monkeypatch):
    monkeypatch.setattr("engine.geo.BAN_URL", str(mock_ban.make_url("/search/")))
    async with ClientSession() as s:
        assert await geocode_city(s, "Zzzville") is None


async def test_geocode_city_empty_returns_none():
    assert await geocode_city(None, "") is None  # pas d'appel réseau si ville vide


async def test_fill_latlon_uses_cache(monkeypatch):
    b = Brain(":memory:")
    b.set_city_geo("Lyon", 45.75, 4.85)
    called = {"n": 0}
    async def fake_geocode(session, city):
        called["n"] += 1
        return (0.0, 0.0)
    monkeypatch.setattr("engine.geo.geocode_city", fake_geocode)
    payload = {"location_city": "Lyon"}
    await fill_latlon(b, None, payload)
    assert payload["lat"] == 45.75 and payload["lon"] == 4.85
    assert called["n"] == 0  # cache hit → aucun appel réseau


async def test_fill_latlon_geocodes_and_caches(monkeypatch):
    b = Brain(":memory:")
    async def fake_geocode(session, city):
        return (48.85, 2.35)
    monkeypatch.setattr("engine.geo.geocode_city", fake_geocode)
    payload = {"location_city": "Paris"}
    await fill_latlon(b, None, payload)
    assert payload["lat"] == 48.85 and payload["lon"] == 2.35
    assert b.get_city_geo("Paris") == (48.85, 2.35)  # mis en cache


async def test_fill_latlon_no_city_is_noop():
    b = Brain(":memory:")
    payload = {}
    await fill_latlon(b, None, payload)
    assert "lat" not in payload and "lon" not in payload


async def test_fill_latlon_geocode_fail_leaves_payload_untouched(monkeypatch):
    b = Brain(":memory:")
    async def fake_geocode(session, city):
        return None
    monkeypatch.setattr("engine.geo.geocode_city", fake_geocode)
    payload = {"location_city": "Inconnue"}
    await fill_latlon(b, None, payload)
    assert "lat" not in payload  # échec géocodage → best-effort, rien ajouté
```

- [ ] **Step 2: Lancer → échec**

Run: `python -m pytest tests/test_engine_geo.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'engine.geo'`).

- [ ] **Step 3: Écrire `engine/geo.py`**

```python
"""Géocodage des villes via l'API BAN (gratuite, sans clé) + remplissage lat/lon.

Best-effort : tout échec (réseau, ville inconnue) laisse lat/lon absents — jamais bloquant.
Cache dans le Brain (table city_geo) pour ne géocoder chaque ville qu'une fois.
"""

BAN_URL = "https://api-adresse.data.gouv.fr/search/"


async def geocode_city(session, city: str):
    """Retourne (lat, lon) pour une ville via la BAN, ou None. Best-effort."""
    city = (city or "").strip()
    if not city:
        return None
    try:
        async with session.get(BAN_URL, params={"q": city, "limit": "1"}) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
        feats = data.get("features") or []
        if not feats:
            return None
        lon, lat = feats[0]["geometry"]["coordinates"]  # GeoJSON = [lon, lat]
        return (float(lat), float(lon))
    except Exception:
        return None


async def fill_latlon(brain, session, payload: dict) -> None:
    """Renseigne payload['lat']/['lon'] depuis la ville (cache Brain → BAN). In-place, best-effort."""
    city = payload.get("location_city")
    if not city:
        return
    cached = brain.get_city_geo(city)
    if cached is not None:
        lat, lon = cached
    else:
        geo = await geocode_city(session, city)
        if geo is None:
            return
        lat, lon = geo
        brain.set_city_geo(city, lat, lon)
    payload["lat"] = lat
    payload["lon"] = lon
```

- [ ] **Step 4: Lancer → succès**

Run: `python -m pytest tests/test_engine_geo.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add engine/geo.py tests/test_engine_geo.py
git commit -m "feat(engine): geocodage BAN + fill_latlon avec cache (proximite)"
```

---

## Task 3 : Brancher le géocodage dans `enrich.py`

**Files:**
- Modify: `engine/enrich.py` (import + 1 appel avant l'insertion)

- [ ] **Step 1: Ajouter l'import**

Dans `engine/enrich.py`, après `from engine.supa import merge_enrichment` :

```python
from engine.geo import fill_latlon
```

- [ ] **Step 2: Remplir lat/lon avant la 1ʳᵉ insertion**

Dans `enrich_once`, remplacer le bloc (lignes ~67-73) :

```python
        payload = merge_enrichment(item["payload"], {
            "category": t["category"], "resale_score": t["score"],
        })
        try:
            await supa.insert_opportunity(payload)  # écriture post-triage (jamais brute)
        except Exception:
            brain.queue_outbox(payload)  # Supabase down → outbox (résilience Phase A)
```

par :

```python
        payload = merge_enrichment(item["payload"], {
            "category": t["category"], "resale_score": t["score"],
        })
        # Géocodage best-effort : remplit lat/lon depuis la ville (cache → BAN). Pour la proximité.
        await fill_latlon(brain, supa.session, payload)
        try:
            await supa.insert_opportunity(payload)  # écriture post-triage (jamais brute)
        except Exception:
            brain.queue_outbox(payload)  # Supabase down → outbox (résilience Phase A)
```

> `payload` est ensuite réutilisé (merge post-vérif) : `merge_enrichment` recopie le dict, donc
> `lat/lon` sont conservés pour la mise à jour ultérieure. Une seule pose suffit.
> `supa.session` existe (cf. `Supa.__init__`).

- [ ] **Step 3: Non-régression**

Run: `python -m pytest tests/test_engine_enrich.py tests/ -q`
Expected: PASS (toute la suite ; `fill_latlon` sans `location_city`/`session` mockée n'altère pas les tests existants — ils n'ont pas de ville ou tolèrent l'appel).

> ⚠️ Si un test d'`enrich` échoue parce que `supa.session` n'existe pas sur le faux client, c'est que
> le fake `supa` du test n'a pas d'attribut `session`. Dans ce cas, ajouter `session=None` au fake et
> vérifier que `fill_latlon` court-circuite (pas de `location_city` dans ces payloads de test → noop).

- [ ] **Step 4: Commit**

```bash
git add engine/enrich.py
git commit -m "feat(engine): remplit opportunities.lat/lon a l'enrichissement (proximite)"
```

---

## Task 4 : `lat`/`lon` dans le SELECT du feed

**Files:**
- Modify: `js/lib/opportunities.js` (constante `SELECT`)

- [ ] **Step 1: Ajouter les champs**

Dans `js/lib/opportunities.js`, remplacer la ligne du `SELECT` :

```javascript
  'location_city', 'location_postal', 'category', 'resale_score',
```

par :

```javascript
  'location_city', 'location_postal', 'lat', 'lon', 'category', 'resale_score',
```

- [ ] **Step 2: Vérifier (console)**

Serveur lancé, connecté, console F12 :
```js
const m = await import('/js/lib/opportunities.js?v=' + Date.now());
const list = await m.listOpportunities({ limit: 1 });
console.log('lat' in (list[0] || {}), 'lon' in (list[0] || {}));
```
Expected: `true true` (si au moins une opportunité existe ; sinon liste vide = ok aussi).

- [ ] **Step 3: Commit**

```bash
git add js/lib/opportunities.js
git commit -m "feat(feed): lat/lon dans le SELECT des opportunites (proximite)"
```

---

## Task 5 : `js/lib/geo-home.js` (domicile + rayon + distance)

**Files:**
- Create: `js/lib/geo-home.js`

- [ ] **Step 1: Créer le fichier**

```javascript
// js/lib/geo-home.js
// Domicile du membre + rayon, en localStorage (pas de DB). Géocodage via l'API BAN gratuite.
const KEY_HOME = 'lbc-home';      // { label, lat, lon }
const KEY_RADIUS = 'lbc-radius';  // '5' | '10' | '25' | '50' | '100' | 'all'
const BAN_URL = 'https://api-adresse.data.gouv.fr/search/';

/** Domicile mémorisé { label, lat, lon } ou null. */
export function getHome() {
  try { return JSON.parse(localStorage.getItem(KEY_HOME)) || null; }
  catch (_) { return null; }
}

export function clearHome() {
  try { localStorage.removeItem(KEY_HOME); } catch (_) {}
}

/** Géocode un code postal/ville via la BAN, mémorise et renvoie { label, lat, lon }. */
export async function setHome(query) {
  const q = (query || '').trim();
  if (!q) throw new Error('Indique un code postal ou une ville.');
  const resp = await fetch(`${BAN_URL}?q=${encodeURIComponent(q)}&limit=1`);
  if (!resp.ok) throw new Error('Géocodage indisponible, réessaie.');
  const data = await resp.json();
  const feat = (data.features || [])[0];
  if (!feat) throw new Error('Lieu introuvable.');
  const [lon, lat] = feat.geometry.coordinates;  // GeoJSON = [lon, lat]
  const home = { label: feat.properties.label, lat, lon };
  try { localStorage.setItem(KEY_HOME, JSON.stringify(home)); } catch (_) {}
  return home;
}

/** Rayon choisi ('all' par défaut). */
export function getRadius() {
  try { return localStorage.getItem(KEY_RADIUS) || 'all'; }
  catch (_) { return 'all'; }
}
export function setRadius(value) {
  try { localStorage.setItem(KEY_RADIUS, String(value)); } catch (_) {}
}

/** Distance en km entre deux points (Haversine). */
export function haversineKm(lat1, lon1, lat2, lon2) {
  const R = 6371, toRad = d => d * Math.PI / 180;
  const dLat = toRad(lat2 - lat1), dLon = toRad(lon2 - lon1);
  const a = Math.sin(dLat / 2) ** 2
    + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}
```

- [ ] **Step 2: Vérifier (console)**

Serveur lancé, console F12 :
```js
const m = await import('/js/lib/geo-home.js?v=' + Date.now());
console.log(Math.round(m.haversineKm(48.85, 2.35, 45.75, 4.85))); // ~392 (Paris-Lyon)
```
Expected: ~392, aucune erreur.

- [ ] **Step 3: Commit**

```bash
git add js/lib/geo-home.js
git commit -m "feat(feed): lib domicile + rayon + haversine (proximite)"
```

---

## Task 6 : Brancher le filtre rayon dans le feed

**Files:**
- Modify: `js/pages/feed.js` (imports, toolbar, events, `renderList`)
- Modify: `js/components/opportunity-row.js` (afficher la distance)

- [ ] **Step 1: `opportunity-row.js` — paramètre `distanceKm`**

Dans `js/components/opportunity-row.js`, remplacer la signature :

```javascript
export function opportunityRowHtml(o, { isFav = false, commentCount = 0, hasNewComments = false } = {}) {
```

par :

```javascript
export function opportunityRowHtml(o, { isFav = false, commentCount = 0, hasNewComments = false, distanceKm = null } = {}) {
```

Puis, dans le `<span class="opp-meta">`, ajouter l'affichage distance. Remplacer :

```javascript
        <span class="opp-meta">${o.location_city ? `📍 ${esc(o.location_city)}` : ''}${
          commentCount > 0
            ? ` <span class="opp-comments">💬 ${commentCount}${hasNewComments ? '<span class="opp-new-dot" title="Nouveaux commentaires"></span>' : ''}</span>`
            : ''}</span>
```

par :

```javascript
        <span class="opp-meta">${o.location_city ? `📍 ${esc(o.location_city)}` : ''}${
          distanceKm != null ? ` <span class="opp-dist">· à ~${Math.round(distanceKm)} km</span>` : ''}${
          commentCount > 0
            ? ` <span class="opp-comments">💬 ${commentCount}${hasNewComments ? '<span class="opp-new-dot" title="Nouveaux commentaires"></span>' : ''}</span>`
            : ''}</span>
```

- [ ] **Step 2: `feed.js` — imports**

Dans `js/pages/feed.js`, après `import { isUnseen } from '../lib/comment-seen.js';` :

```javascript
import { getHome, setHome, getRadius, setRadius, haversineKm } from '../lib/geo-home.js';
```

- [ ] **Step 3: `feed.js` — ajouter la rangée secteur+rayon dans la toolbar**

Dans le HTML de `render()`, juste après la `<div class="row" id="feedChips">…</div>` (la rangée des chips), ajouter une nouvelle rangée :

```javascript
        <div class="row" id="feedGeo">
          <input class="feed-search" id="feedSecteur" placeholder="📍 Mon secteur (code postal ou ville)">
          <select id="feedRadius">
            <option value="all">Toute la France</option>
            <option value="5">≤ 5 km</option>
            <option value="10">≤ 10 km</option>
            <option value="25">≤ 25 km</option>
            <option value="50">≤ 50 km</option>
            <option value="100">≤ 100 km</option>
          </select>
          <span class="feed-geo-msg" id="feedGeoMsg"></span>
        </div>
```

- [ ] **Step 4: `feed.js` — initialiser les contrôles + événements**

Juste après le bloc des événements toolbar existants (après le listener de `feedFav`, avant la délégation favoris), ajouter :

```javascript
  // Secteur + rayon (proximité). État pré-rempli depuis localStorage.
  const secteurEl = document.getElementById('feedSecteur');
  const radiusEl = document.getElementById('feedRadius');
  const geoMsg = document.getElementById('feedGeoMsg');
  const home0 = getHome();
  if (home0) secteurEl.value = home0.label;
  radiusEl.value = getRadius();
  if (home0) geoMsg.textContent = `📍 ${home0.label}`;
  secteurEl.addEventListener('change', async () => {
    const q = secteurEl.value.trim();
    if (!q) return;
    geoMsg.textContent = '⏳ Localisation…';
    try {
      const home = await setHome(q);
      geoMsg.textContent = `📍 ${home.label}`;
      renderList();
    } catch (err) {
      geoMsg.textContent = '❌ ' + err.message;
    }
  });
  radiusEl.addEventListener('change', () => { setRadius(radiusEl.value); renderList(); });
```

- [ ] **Step 5: `feed.js` — appliquer le filtre dans `renderList`**

Remplacer le corps de `renderList` (à partir de `const finalList = …`) par :

```javascript
    let finalList = state.favOnly ? list.filter(o => isFav(o.id)) : list;
    // Filtre proximité : si domicile défini ET rayon ≠ "Toute la France".
    const home = getHome();
    const radius = getRadius();
    if (home && radius !== 'all') {
      const rad = Number(radius);
      finalList = finalList.filter(o =>
        o.lat != null && o.lon != null && haversineKm(home.lat, home.lon, o.lat, o.lon) <= rad);
    }
    empty.classList.toggle('hidden', state.items.length > 0);
    grid.innerHTML = finalList.map(o => {
      const meta = commentMeta.get(o.id);
      const dist = (home && o.lat != null && o.lon != null)
        ? haversineKm(home.lat, home.lon, o.lat, o.lon) : null;
      return opportunityRowHtml(o, {
        isFav: isFav(o.id),
        commentCount: meta ? meta.count : 0,
        hasNewComments: !!(meta && meta.participated && isUnseen(o.id, meta.latest)),
        distanceKm: dist,
      });
    }).join('');
    count.textContent = `${finalList.length} opportunité${finalList.length > 1 ? 's' : ''}`;
```

> (Ce bloc remplace l'ancien `const finalList = …; empty…; grid.innerHTML = …; count… ;` introduit en C-4.)

- [ ] **Step 6: Vérifier (page + console)**

Serveur lancé, connecté, `/feed` :
- Renseigner un code postal/ville dans « Mon secteur » → `📍 <label>` s'affiche.
- Choisir « ≤ 50 km » → la liste se filtre ; les lignes avec coords montrent « · à ~X km ».
- « Toute la France » → tout revient.
- **Console F12 propre** ; le compteur et les filtres catégorie/favoris/recherche marchent encore (non-régression C-1/C-4).

> Rappel : seules les opportunités **géocodées par le moteur** (lat/lon non nuls) apparaissent quand un
> rayon est actif. Les anciennes (sans coords) n'apparaissent que sous « Toute la France ».

- [ ] **Step 7: Commit**

```bash
git add js/pages/feed.js js/components/opportunity-row.js
git commit -m "feat(feed): filtre par rayon + distance affichee (proximite)"
```

---

## Task 7 : Styles secteur/rayon/distance

**Files:**
- Modify: `style.css` (append)

- [ ] **Step 1: Ajouter le bloc**

Append à la fin de `style.css` :

```css
/* ===== Proximité : secteur + rayon + distance ===== */
#feedGeo { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-top: 8px; }
#feedGeo #feedSecteur { flex: 1; min-width: 180px; }
#feedGeo #feedRadius {
  padding: 8px 10px; border-radius: 10px; background: rgba(255,255,255,.05);
  color: inherit; border: 1px solid rgba(255,255,255,.12);
}
.feed-geo-msg { font-size: .8rem; color: var(--c-mut, #94a3b8); }
.opp-dist { color: var(--c-mut, #94a3b8); }
```

- [ ] **Step 2: Vérifier le rendu**

Recharger `/feed` : la rangée secteur+rayon est alignée et cohérente avec la DA ; « · à ~X km » discret. Console F12 propre.

- [ ] **Step 3: Commit**

```bash
git add style.css
git commit -m "feat(feed): styles secteur/rayon/distance (proximite)"
```

---

## Validation finale (E2E manuel)

Serveur lancé, connecté, sur `/feed` :
1. Renseigner « Mon secteur » (ex. ton code postal) → `📍 <ville>` s'affiche, persiste après reload.
2. Choisir un rayon (ex. ≤ 25 km) → seules les opportunités géocodées dans le rayon restent, avec « · à ~X km ».
3. « Toute la France » → toutes reviennent.
4. Les filtres catégorie / favoris / recherche / tri fonctionnent toujours en combinaison. Console F12 propre.
5. (moteur) Après quelques passes avec géocodage, `opportunities.lat/lon` se remplissent (vérifiable dans Supabase) et le cache `city_geo` évite les appels BAN répétés.

---

## Self-Review

**Couverture spec :**
- Cache `city_geo` (Brain) → Task 1 ✅
- `engine/geo.py` (`geocode_city` BAN best-effort + `fill_latlon` cache→BAN) → Task 2 ✅
- Remplissage `opportunities.lat/lon` à l'écriture (enrich.py) → Task 3 ✅
- `lat/lon` lus par le feed → Task 4 ✅
- Domicile localStorage + rayon + Haversine (géocodage BAN navigateur) → Task 5 ✅
- Toolbar secteur+rayon + filtre distance + « à ~X km » → Task 6 ✅
- Items sans coords exclus quand rayon actif, visibles sous « Toute la France » → Task 6 Step 5 (`o.lat != null && …`) ✅
- Styles → Task 7 ✅
- Pas de migration / distance hors note IA → respecté (aucune touche au scoring) ✅

**Cohérence des types/signatures :** `get_city_geo(city)->(lat,lon)|None` / `set_city_geo(city,lat,lon,now=None)` (Task 1) utilisés par `fill_latlon` (Task 2). `geocode_city(session,city)->(lat,lon)|None` et `fill_latlon(brain,session,payload)` (Task 2) appelés en Task 3 (`fill_latlon(brain, supa.session, payload)`). `getHome()/setHome()/getRadius()/setRadius()/haversineKm()` (Task 5) consommés en Task 6. `opportunityRowHtml(o, {…, distanceKm})` (Task 6 Step 1) appelé avec `distanceKm` (Step 5). Cohérent.

**Placeholders :** aucun ; code complet partout.
