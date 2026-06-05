# Journal de trading (groupe) — Design Spec

**Date :** 2026-06-05
**Statut :** validé

## Contexte

Le `/dashboard` actuel est un carnet d'achats/ventes **individuel et privé** (table
`transactions`, opérations indépendantes). On le **remplace** par un **Journal de trading
partagé** : chaque deal est suivi de bout en bout (Contacté → Acheté → Revendu), visible par
tout le groupe, avec liaison aux opportunités du feed. Le Journal devient l'outil unique de
suivi de l'argent (il absorbe le rôle de l'ancien dashboard).

## Décisions de design (toutes validées)

| Sujet | Décision |
|---|---|
| Données | Nouvelle table `trades` (repart de zéro ; l'ancienne `transactions` est abandonnée, laissée dormante) |
| Visibilité | **Partagé** : tous les membres voient tous les deals (bilan groupe) |
| Écriture | Auteur (`user_id = auth.uid()`) ou admin |
| Route | **Remplace `/dashboard`** ; l'onglet de nav est renommé « Journal » |
| Cycle | **Flexible** : un deal peut démarrer directement à « Acheté » ou « Revendu » |
| Liaison feed | Recherche dans le modal **+** bouton « ➕ Ajouter au journal » depuis `/item/:id` |
| Anim. d'entrée | **Colonnes qui glissent** (KPIs en fondu haut + 3 colonnes Kanban depuis les côtés) |
| Anim. transition | Picto « livre » (déjà livré, route `/dashboard`) |

## Table `trades` (migration SQL)

`supabase/migrations/2026-06-05-trades.sql` :

```sql
create table if not exists public.trades (
    id              uuid primary key default gen_random_uuid(),
    user_id         uuid not null references auth.users(id) on delete cascade,
    opportunity_id  uuid references public.opportunities(id) on delete set null,
    title           text not null check (char_length(title) between 1 and 200),
    status          text not null default 'contacted'
                       check (status in ('contacted', 'bought', 'sold')),
    buy_price       numeric(10,2) check (buy_price is null or buy_price >= 0),
    sell_price      numeric(10,2) check (sell_price is null or sell_price >= 0),
    bought_at       date,
    sold_at         date,
    notes           text,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);

-- FK indexées (perf JOIN + ON DELETE)
create index if not exists trades_user_id_idx       on public.trades (user_id);
create index if not exists trades_opportunity_id_idx on public.trades (opportunity_id);
-- Tri courant : par date de mise à jour décroissante
create index if not exists trades_updated_idx       on public.trades (updated_at desc);

alter table public.trades enable row level security;

-- Lecture : tous les membres authentifiés (journal partagé)
drop policy if exists "trades_select_all" on public.trades;
create policy "trades_select_all" on public.trades
    for select to authenticated using (true);

-- Écriture : auteur ou admin (helper inline via sous-requête sur profiles)
drop policy if exists "trades_insert_own" on public.trades;
create policy "trades_insert_own" on public.trades
    for insert to authenticated
    with check ((select auth.uid()) = user_id);

drop policy if exists "trades_update_own_or_admin" on public.trades;
create policy "trades_update_own_or_admin" on public.trades
    for update to authenticated
    using (
        (select auth.uid()) = user_id
        or exists (select 1 from public.profiles p
                   where p.id = (select auth.uid()) and p.role = 'admin')
    );

drop policy if exists "trades_delete_own_or_admin" on public.trades;
create policy "trades_delete_own_or_admin" on public.trades
    for delete to authenticated
    using (
        (select auth.uid()) = user_id
        or exists (select 1 from public.profiles p
                   where p.id = (select auth.uid()) and p.role = 'admin')
    );

-- updated_at auto à chaque UPDATE
create or replace function public.touch_trades_updated_at()
returns trigger language plpgsql as $$
begin new.updated_at = now(); return new; end; $$;

drop trigger if exists trg_trades_touch on public.trades;
create trigger trg_trades_touch before update on public.trades
    for each row execute function public.touch_trades_updated_at();
```

> Realtime optionnel (non requis v1) : le Journal recharge à chaque ouverture + après
> chaque CRUD local. On pourra ajouter un canal realtime plus tard si besoin.

## Accès données — `js/lib/trades.js`

Nouveau module (remplace l'usage de `transactions.js` dans le dashboard) :

```javascript
const SELECT = 'id, user_id, opportunity_id, title, status, buy_price, sell_price, ' +
  'bought_at, sold_at, notes, created_at, updated_at, author:profiles(username, avatar_color)';

export async function listTrades()                 // tous les deals (RLS partagée), tri updated_at desc
export async function createTrade(payload)         // insert (user_id = moi)
export async function updateTrade(id, payload)     // update (RLS auteur/admin)
export async function deleteTrade(id)              // delete (RLS auteur/admin)
export async function searchOpportunities(query)   // recherche feed pour la liaison (title ilike, limit 8)
export function computeGroupKpis(trades)           // { invested, earned, profit, roi, counts par statut }
export function buildMonthlySeries(trades)         // cumul achats/ventes + profit mensuel (pour les graphes)
```

- `computeGroupKpis` (profit **réalisé**, périmètre cohérent) :
  - `invested` = Σ `buy_price` des deals **revendus** (ceux dont le cycle est bouclé)
  - `earned` = Σ `sell_price` des deals **revendus**
  - `profit` = Σ (`sell_price` − `buy_price`) sur les **revendus** (= earned − invested)
  - `roi` = `invested > 0 ? profit / invested : null`
  - `counts` = nombre de deals par statut (pour les en-têtes de colonnes Kanban)
  > On ne mélange pas les achats en cours (non revendus) dans le profit : le profit affiché
  > est la **marge réalisée** du groupe. Les achats en cours restent visibles dans la colonne
  > « Achetés » mais n'impactent pas le profit tant qu'ils ne sont pas revendus.
- `searchOpportunities(query)` : `select id,title,price,category from opportunities where
  title ilike %query% order by created_at desc limit 8`.

## Page `/dashboard` → « Journal » (`js/pages/dashboard.js`, réécrite)

Structure (DA actuelle : thème clair, accent orange, glassmorphism) :

### En-tête héro
- Eyebrow « Journal · revente groupe »
- Chiffre principal : **Profit net du groupe** (couleur selon signe)
- Sous-ligne : ROI · N revendus / N achetés / N contactés
- Bouton **➕ Ajouter un deal**

### KPIs (4 cartes)
💰 Total investi · 💵 Total encaissé · 📈 Profit net · 🎯 ROI (réutilise le style `dash-kpi`).

### Graphiques (2, Chart.js lazy-load existant, adaptés aux `trades`)
- Cumul achats vs ventes (par mois)
- Profit net mensuel
- Fallback gracieux si le CDN Chart.js est injoignable (déjà géré dans le dashboard actuel : on garde la logique).

### Kanban — 3 colonnes par statut
- **🤝 Contactés** · **🛒 Achetés** · **✅ Revendus** (compteur par colonne)
- Carte deal : titre (+ lien feed si `opportunity_id`), avatar+pseudo de l'auteur,
  prix d'achat / de vente selon le statut, **marge** (vente − achat) en vert si revendu,
  boutons ✏️ Modifier / 🗑️ Supprimer (visibles si auteur ou admin).
- Clic sur une carte (hors boutons) → ouvre le modal d'édition (permet de faire avancer le statut).
- État vide par colonne : court message discret.

### Animation d'entrée (option C)
Au premier rendu : les **KPIs** apparaissent en fondu depuis le haut ; les **3 colonnes**
glissent — gauche depuis la gauche, centre en fondu/montée, droite depuis la droite. Classe
`.journal-enter` posée sur le conteneur, retirée après l'animation (≈ 0,6s). Respecte
`prefers-reduced-motion` (pas de translation).

## Modal d'ajout / édition

Réutilise le style `modal-overlay` / `modal-card` existant. Champs :

**Toujours :**
- **Article** (titre, requis, max 200) — pré-rempli si liaison feed / venu de `/item/:id`
- **Statut** — toggle 3 positions : 🤝 Contacté · 🛒 Acheté · ✅ Revendu
- **Lier une annonce** (optionnel) — champ de recherche : tape → `searchOpportunities` →
  liste (titre · prix · 🔴/🟡/⚫) → sélection remplit le titre + mémorise `opportunity_id`.
  Bouton « ✕ délier » pour retirer la liaison.
- **Notes** (optionnel, libre)

**Conditionnels (affichage selon le statut sélectionné, en direct) :**
- Statut ≥ **Acheté** → **Prix d'achat (€)** + **Date d'achat** (défaut : aujourd'hui)
- Statut = **Revendu** → **Prix de vente (€)** + **Date de vente** (défaut : aujourd'hui)
- Quand les deux prix sont présents → **marge calculée affichée en direct** sous les champs.

**Validation :**
- Titre requis (1–200 caractères).
- Statut = **Acheté** ou **Revendu** → **prix d'achat requis** (nombre ≥ 0).
- Statut = **Revendu** → **prix de vente requis** (nombre ≥ 0).
- Statut = **Contacté** → aucun prix requis (champs prix masqués, envoyés `null`).
- Dates : optionnelles ; si le statut implique l'étape mais qu'aucune date n'est saisie, on
  met la date du jour par défaut côté formulaire. Format ISO `YYYY-MM-DD`.

**Payload envoyé :** `{ title, status, buy_price, sell_price, bought_at, sold_at, notes,
opportunity_id }` (les champs non pertinents au statut sont mis à `null`).

## Bouton « ➕ Ajouter au journal » sur `/item/:id`

Dans `js/pages/item.js`, sous le bouton « Voir l'annonce sur Leboncoin », ajouter un bouton
**➕ Ajouter au journal**. Au clic : navigue vers `/dashboard` en passant l'opportunité à
pré-remplir. Implémentation : on stocke l'item à ajouter dans un petit relais
(`sessionStorage 'journal-prefill'` = `{ opportunity_id, title }`), puis `/dashboard` détecte
ce relais au montage, ouvre le modal pré-rempli (statut « Contacté ») et nettoie le relais.

> Choix : `sessionStorage` (et non query param) pour rester cohérent avec le routing SPA et ne
> pas exposer de données dans l'URL. Mono-onglet (cf. piège connu #5), acceptable ici.

## Navigation

`js/components/header.js` : l'entrée dock `{ href:'/dashboard', label:'Dashboard' }` devient
`label: 'Journal'` (icône `book` si dispo dans `icons.js`, sinon garder `chart`).

## Fichiers modifiés / créés

| Fichier | Action |
|---|---|
| `supabase/migrations/2026-06-05-trades.sql` | Créer (table + RLS + trigger) |
| `js/lib/trades.js` | Créer (CRUD + recherche + KPIs + séries) |
| `js/pages/dashboard.js` | Réécrire (Journal : héro + KPIs + graphes + Kanban + modal + anim C) |
| `js/pages/item.js` | Modifier (bouton « ➕ Ajouter au journal » + relais sessionStorage) |
| `js/components/header.js` | Modifier (label « Journal ») |
| `style.css` | Modifier (Kanban, cartes deal, anim d'entrée C, modal recherche feed) |

## Hors scope (v1)

- Glisser-déposer des cartes entre colonnes (le statut change via le modal). Drag-drop = plus tard.
- Realtime sur `trades` (rechargement au montage + après CRUD suffit pour v1).
- Suppression effective de l'ancienne table `transactions` et de `js/lib/transactions.js`
  (laissées dormantes ; nettoyage SQL séparé, comme les autres tables legacy).
- Boutons « avancer le statut » en un clic sur la carte (raffinement futur).
- Rapport hebdo / classement marges (feature « Tendances », Phase E).

## Tests

Convention projet : **pas de tests frontend** (validation manuelle : page + console F12).
Pas de code backend ici (tout passe par le SDK Supabase + RLS). Validation E2E manuelle :
créer/éditer/supprimer un deal, faire avancer un statut, lier une annonce, vérifier les KPIs
et le bilan groupe, tester depuis deux comptes (partagé), et le bouton depuis `/item/:id`.
