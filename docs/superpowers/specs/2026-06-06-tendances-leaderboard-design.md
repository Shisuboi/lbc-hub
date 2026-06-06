# Tendances — Leaderboard groupe dans le Journal — Design

- **Date** : 2026-06-06
- **Projet** : LBC DealFinder Hub (`lbc-hub`)
- **Statut** : Spec validée
- **Auteur** : Claude (technique) + Tristan (produit)

---

## 1. Objectif

Ajouter une section **« Classement du groupe »** dans la page `/dashboard` (Journal de trading)
qui montre, en une liste triée, quel membre a généré le plus de profit net sur ses deals revendus.

Périmètre de cette phase : **leaderboard uniquement**.
Hors-champ : rapport Telegram hebdo, market stats par catégorie.

---

## 2. Données

Aucun appel Supabase supplémentaire. La section consomme **`state.trades`** déjà chargé par
`listTrades()` au montage de la page.

Seuls les deals au statut **`sold`** entrent dans le calcul (les deals `contacted` / `bought`
ne représentent pas du profit réalisé). Un membre sans deal `sold` n'apparaît pas dans le
classement.

### Calcul par membre

Pour chaque `user_id` distinct dans les trades `sold` :

| Métrique | Formule |
|---|---|
| `invested` | Σ `buy_price` des deals sold |
| `earned` | Σ `sell_price` des deals sold |
| `profit` | `earned − invested` |
| `roi` | `(profit / invested) × 100` (null si `invested = 0`) |
| `soldCount` | Nombre de deals sold |

Tri : **profit décroissant**. En cas d'égalité : `soldCount` décroissant.

---

## 3. Architecture

### 3.1 Nouvelle fonction `computeLeaderboard(trades)` dans `js/lib/trades.js`

Fonction **pure** (pas d'effet de bord, pas d'appel réseau) :

```
computeLeaderboard(trades) → [
  { user_id, username, avatar_color, profit, roi, soldCount, invested, earned },
  ...
]  // trié par profit desc
```

Elle est testable en isolation (même pattern que `computeGroupKpis`).

### 3.2 Section HTML dans `js/pages/dashboard.js`

Ajoutée dans le template `render()` entre `#jrCharts` et `#jrBoard`.

```html
<div class="jr-leaderboard card hidden" id="jrLeaderboard">
  <h3 class="jr-leaderboard-title">🏆 Classement du groupe</h3>
  <ol class="jr-lb-list" id="jrLbList"></ol>
</div>
```

### 3.3 Fonction `renderLeaderboard()` dans `dashboard.js`

Appelée depuis `renderAll()`, après `renderKpis()`. Masquée si aucun deal `sold`.

Chaque ligne :
```
#N  [avatar]  pseudo   +XX €  (XX %)  · N revendu(s)
```

La ligne `#1` porte la classe `jr-lb-gold` (accent doré).

### 3.4 Styles `.jr-leaderboard` dans `style.css`

Bloc CSS ajouté en fin de fichier (pattern du projet).

---

## 4. Placement dans la page

```
[Héro profit net]
[KPIs 4 cartes]
[Graphiques (si deals)]
[Classement du groupe  ← NOUVEAU, masqué si 0 deal sold]
[Kanban 3 colonnes]
[État vide (si 0 deal)]
```

---

## 5. États

| Condition | Comportement |
|---|---|
| 0 deal `sold` dans le groupe | Section masquée (`.hidden`) |
| 1+ deal `sold` | Section visible, liste triée |
| Membre sans deal `sold` | Non affiché dans la liste |
| `invested = 0` sur un deal sold | ROI affiché `n/d` |

---

## 6. Fichiers modifiés

| Fichier | Action |
|---|---|
| `js/lib/trades.js` | Ajouter `computeLeaderboard(trades)` (export) |
| `js/pages/dashboard.js` | Ajouter HTML section + `renderLeaderboard()` + appel dans `renderAll()` + import |
| `style.css` | Ajouter bloc `.jr-leaderboard` en fin de fichier |

Aucune migration Supabase. Aucun nouvel endpoint. Aucun nouveau fichier.

---

## 7. Hors-champ

- Rapport hebdo Telegram — phase ultérieure
- Stats par catégorie d'objet — phase ultérieure
- Market stats (prix marché par catégorie depuis `market_observations`) — phase ultérieure
