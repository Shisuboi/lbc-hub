# Tendances v1 — Leaderboard groupe dans le Journal — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter une section « 🏆 Classement du groupe » dans `/dashboard`, entre les graphiques et le Kanban, affichant les membres triés par profit net réalisé sur leurs deals revendus.

**Architecture:** Nouvelle fonction pure `computeLeaderboard(trades)` dans `js/lib/trades.js`, consommant `state.trades` déjà chargé (zéro appel Supabase supplémentaire). Section HTML + `renderLeaderboard()` ajoutées à `js/pages/dashboard.js`. Section masquée si aucun deal `sold`.

**Tech Stack:** Vanilla JS ES6, Supabase SDK v2. **Pas de tests frontend** (Node absent) → validation manuelle console F12 + rendu visuel. Serveur dev = `python server.py`.

---

## File Structure

| Fichier | Action | Responsabilité |
|---|---|---|
| `js/lib/trades.js` | Modifier | Ajouter `computeLeaderboard(trades)` (export) |
| `js/pages/dashboard.js` | Modifier | Import + HTML section + `renderLeaderboard()` + appel dans `renderAll()` |
| `style.css` | Modifier | Append bloc `.jr-leaderboard` en fin de fichier |

---

## Task 1 : `computeLeaderboard` dans `js/lib/trades.js`

**Files:**
- Modify: `js/lib/trades.js`

- [ ] **Step 1 : Ajouter la fonction en fin de fichier**

À la toute fin de `js/lib/trades.js`, après `buildMonthlySeries`, ajouter :

```javascript
/**
 * Classement des membres par profit net réalisé (deals sold uniquement).
 * Renvoie un tableau trié profit desc, un entry par user_id distinct.
 */
export function computeLeaderboard(trades) {
  const byUser = new Map();
  for (const t of trades) {
    if (t.status !== 'sold') continue;
    if (!byUser.has(t.user_id)) {
      byUser.set(t.user_id, {
        user_id: t.user_id,
        username: t.author?.username || 'Anonyme',
        avatar_color: t.author?.avatar_color || 'var(--accent)',
        invested: 0,
        earned: 0,
        soldCount: 0,
      });
    }
    const m = byUser.get(t.user_id);
    m.invested += Number(t.buy_price || 0);
    m.earned += Number(t.sell_price || 0);
    m.soldCount++;
  }
  return [...byUser.values()]
    .map(m => ({
      ...m,
      profit: m.earned - m.invested,
      roi: m.invested > 0 ? ((m.earned - m.invested) / m.invested) * 100 : null,
    }))
    .sort((a, b) => b.profit - a.profit || b.soldCount - a.soldCount);
}
```

- [ ] **Step 2 : Vérifier (console F12, serveur lancé + connecté)**

```js
const m = await import('/js/lib/trades.js?v=' + Date.now());
const fakes = [
  { status:'sold', user_id:'u1', buy_price:80, sell_price:150,
    author:{ username:'Alice', avatar_color:'#6366f1' } },
  { status:'sold', user_id:'u2', buy_price:50, sell_price:90,
    author:{ username:'Bob', avatar_color:'#f43f5e' } },
  { status:'sold', user_id:'u1', buy_price:30, sell_price:80,
    author:{ username:'Alice', avatar_color:'#6366f1' } },
  { status:'contacted', user_id:'u3', author:{ username:'Charlie', avatar_color:'#34d399' } },
];
console.log(m.computeLeaderboard(fakes));
// Attendu :
// [0] Alice  — profit 120 (150-80 + 80-30), soldCount 2
// [1] Bob    — profit 40  (90-50),           soldCount 1
// Charlie (contacted) = absent du tableau
```

- [ ] **Step 3 : Commit**

```bash
git add js/lib/trades.js
git commit -m "feat(tendances): computeLeaderboard — classement membres par profit realise"
```

---

## Task 2 : Section HTML + `renderLeaderboard()` dans `js/pages/dashboard.js`

**Files:**
- Modify: `js/pages/dashboard.js`

- [ ] **Step 1 : Ajouter `computeLeaderboard` à l'import**

Remplacer :

```javascript
import {
  listTrades, createTrade, updateTrade, deleteTrade, searchOpportunities,
  computeGroupKpis, buildMonthlySeries, formatMonthLabel,
} from '../lib/trades.js';
```

par :

```javascript
import {
  listTrades, createTrade, updateTrade, deleteTrade, searchOpportunities,
  computeGroupKpis, buildMonthlySeries, formatMonthLabel, computeLeaderboard,
} from '../lib/trades.js';
```

- [ ] **Step 2 : Insérer la section HTML entre les graphiques et le Kanban**

Remplacer :

```javascript
      </div>

      <div class="jr-board" id="jrBoard">
```

par :

```javascript
      </div>

      <div class="jr-leaderboard card hidden" id="jrLeaderboard">
        <h3 class="jr-leaderboard-title">🏆 Classement du groupe</h3>
        <ol class="jr-lb-list" id="jrLbList"></ol>
      </div>

      <div class="jr-board" id="jrBoard">
```

> La section suit `#jrCharts` (fermeture `</div>`) et précède `#jrBoard`. Elle est `hidden` par défaut ; `renderLeaderboard()` l'affiche si des deals sold existent.

- [ ] **Step 3 : Ajouter `renderLeaderboard()` dans `renderAll()`**

Remplacer :

```javascript
  function renderAll() {
    const has = state.trades.length > 0;
    document.getElementById('jrEmpty').classList.toggle('hidden', has);
    document.getElementById('jrCharts').classList.toggle('hidden', !has);
    document.getElementById('jrBoard').classList.toggle('hidden', !has);
    renderKpis();
    if (has) { renderBoard(); renderCharts(); }
  }
```

par :

```javascript
  function renderAll() {
    const has = state.trades.length > 0;
    document.getElementById('jrEmpty').classList.toggle('hidden', has);
    document.getElementById('jrCharts').classList.toggle('hidden', !has);
    document.getElementById('jrBoard').classList.toggle('hidden', !has);
    renderKpis();
    renderLeaderboard();
    if (has) { renderBoard(); renderCharts(); }
  }
```

- [ ] **Step 4 : Ajouter la fonction `renderLeaderboard()` après `renderKpis()`**

Repérer la ligne de fermeture de `renderKpis()` :

```javascript
    document.getElementById('jrKpis').innerHTML = `
      ${kpi('💰', 'accent-blue', 'Total investi', eur.format(k.invested), 'achats des deals revendus')}
      ${kpi('💵', 'accent-green', 'Total encaissé', eur.format(k.earned), 'ventes réalisées')}
      ${kpi('📈', 'accent-purple', 'Profit net', `${sign}${eur.format(k.profit)}`, 'marge réalisée', pClass)}
      ${kpi('🎯', 'accent-amber', 'ROI', roiTxt, 'retour sur investissement')}`;
  }
```

Ajouter juste après (avant `function cardHtml`) :

```javascript
  function renderLeaderboard() {
    const section = document.getElementById('jrLeaderboard');
    const list = document.getElementById('jrLbList');
    if (!section || !list) return;
    const lb = computeLeaderboard(state.trades);
    if (!lb.length) { section.classList.add('hidden'); return; }
    section.classList.remove('hidden');
    list.innerHTML = lb.map((m, i) => {
      const sign = m.profit >= 0 ? '+' : '';
      const roiTxt = m.roi == null ? 'n/d'
        : `${m.roi > 0 ? '+' : ''}${m.roi.toFixed(1).replace('.', ',')} %`;
      return `<li class="jr-lb-row${i === 0 ? ' jr-lb-gold' : ''}">
        <span class="jr-lb-rank">#${i + 1}</span>
        <span class="jr-avatar" style="background:${esc(m.avatar_color)}">${esc(m.username[0].toUpperCase())}</span>
        <span class="jr-lb-name">${esc(m.username)}</span>
        <span class="jr-lb-profit ${m.profit >= 0 ? 'is-positive' : 'is-negative'}">${sign}${eur2.format(m.profit)}</span>
        <span class="jr-lb-roi muted">${roiTxt}</span>
        <span class="jr-lb-count muted">${m.soldCount} revendu${m.soldCount > 1 ? 's' : ''}</span>
      </li>`;
    }).join('');
  }
```

- [ ] **Step 5 : Vérifier (page + console)**

Serveur lancé, connecté, sur `/dashboard` :
- Si aucun deal `sold` : section absente (`.hidden`), le reste de la page inchangé.
- Créer un deal en statut `sold` (prix achat 80, vente 150) → section apparaît avec une ligne `#1 [avatar] [pseudo] +70,00 € (+87,5 %) 1 revendu`.
- Avec deux membres ayant des deals sold : classement trié par profit décroissant.
- Console F12 propre (aucune erreur).

- [ ] **Step 6 : Commit**

```bash
git add js/pages/dashboard.js
git commit -m "feat(tendances): section leaderboard groupe dans le Journal"
```

---

## Task 3 : Styles `.jr-leaderboard` dans `style.css`

**Files:**
- Modify: `style.css` (append)

- [ ] **Step 1 : Ajouter le bloc CSS à la fin de `style.css`**

```css
/* ===== Tendances : leaderboard groupe ===== */
.jr-leaderboard { margin-top: 18px; }
.jr-leaderboard-title { font-weight: 700; font-size: 1rem; margin-bottom: 12px; }
.jr-lb-list { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 8px; }
.jr-lb-row {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 12px; border-radius: 12px;
  background: rgba(0,0,0,.03);
}
.jr-lb-gold {
  background: rgba(234,179,8,.08);
  border: 1px solid rgba(234,179,8,.22);
}
.jr-lb-rank { font-weight: 700; font-size: .85rem; color: var(--text-secondary, #78716c); min-width: 26px; }
.jr-lb-gold .jr-lb-rank { color: #ca8a04; }
.jr-lb-name { font-weight: 600; font-size: .9rem; flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.jr-lb-profit { font-weight: 700; font-size: .9rem; white-space: nowrap; }
.jr-lb-roi { font-size: .8rem; white-space: nowrap; }
.jr-lb-count { font-size: .78rem; white-space: nowrap; }
@media (max-width: 500px) { .jr-lb-roi { display: none; } }
```

- [ ] **Step 2 : Vérifier le rendu**

Recharger `/dashboard` avec au moins un deal sold :
- Section alignée, lisible, dans la DA du Journal (glassmorphism).
- Ligne #1 avec fond doré subtil.
- Sur mobile (< 500 px) le ROI est masqué, le reste reste lisible.
- Console F12 propre.

- [ ] **Step 3 : Commit**

```bash
git add style.css
git commit -m "feat(tendances): styles leaderboard groupe"
```

---

## Validation finale E2E (manuel)

Serveur lancé, connecté, sur `/dashboard` :
1. **Aucun deal sold** → section absente, page Journal inchangée.
2. **Créer 1 deal sold** (achat 50 €, vente 120 €) → section apparaît : `#1 [moi] +70,00 € (+140,0 %) 1 revendu`.
3. **Ajouter un 2ᵉ deal sold** au même compte (achat 30, vente 60) → même ligne mise à jour : `+100,00 € (+125,0 %) 2 revendus`.
4. **Depuis un 2ᵉ compte** avec meilleur profit → classement trié, #1 change.
5. **Deal "contacted" ou "bought"** → n'apparaît pas dans le leaderboard.
6. Console F12 propre partout.

---

## Self-Review

**Couverture spec :**
- `computeLeaderboard(trades)` pure, groupée par `user_id`, sold seulement, triée profit desc → Task 1 ✅
- Section HTML `#jrLeaderboard` entre `#jrCharts` et `#jrBoard`, `hidden` par défaut → Task 2 ✅
- `renderLeaderboard()` appelée dans `renderAll()`, masquée si 0 deal sold → Task 2 ✅
- Rang #1 accent doré, ROI `n/d` si `invested = 0` → Task 2 + Task 3 ✅
- Styles → Task 3 ✅

**Cohérence des types :**
- `computeLeaderboard(trades)` définie Task 1, importée et appelée Task 2 ✅
- `esc`, `eur2` déjà définis dans `dashboard.js` (helpers existants) → utilisés dans `renderLeaderboard()` ✅
- `state.trades` déjà chargé avant `renderAll()` → `renderLeaderboard()` le consomme sans fetch ✅

**Placeholders :** aucun ; code complet partout.
