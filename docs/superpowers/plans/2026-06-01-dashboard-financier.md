# Plan d'implémentation — Page Tableau de bord financier (`/dashboard`)

**Date** : 2026-06-01
**Version cible** : v1.9.0
**Statut** : En cours d'implémentation
**Révision** : 2 (stratégie front-end + Agent Skills intégrés — **nouvelle source de vérité**)

---

## Objectif

Ajouter une page `/dashboard` permettant à chaque utilisateur de saisir ses transactions (achats et ventes d'articles LBC) et de visualiser ses performances financières via des graphiques interactifs, avec un niveau de finition esthétique de référence (qualité « shadcn / Efferd ») **sans rcompromettre l'architecture zéro-build du projet**.

---

## ⚡ Décisions stratégiques (révision 2) — lire en premier

### D-DASH-01 — Front-end : Vanilla JS/CSS pur, **pas** de Tailwind ni de build step
**Décision** : on **n'introduit ni Tailwind, ni build step, ni dépendance npm**. On atteint le niveau de qualité visuel d'Efferd/shadcn en **CSS pur**, dans le design system dark glassmorphism déjà en place (`style.css`, variables `--accent-*`, polices Bricolage Grotesque/Outfit).

**Justification (en tant que Lead Dev)** :
- Le projet est un SPA Vanilla déployé **tel quel** sur GitHub Pages (push master → live, aucune étape de build). Introduire Tailwind imposerait soit le **Play CDN** (explicitement déconseillé en prod par Tailwind : FOUC, perf, pas de purge), soit un **vrai build step** (Vite/Tailwind CLI) qui obligerait à refondre tout le pipeline de déploiement GitHub Pages pour **une seule page**.
- shadcn est un design system **clair, orienté React**. L'app entière est en **dark theme maison cohérent sur 9 routes**. Greffer son esthétique claire créerait une **incohérence visuelle** sur une page isolée.
- La qualité « Efferd » ne tient pas au framework mais à la **rigueur du design** (hiérarchie typographique, espacement généreux, bordures/ombres subtiles, labels muted + chiffres en gras, icônes discrètes). Tout cela est atteignable — et l'est ici — en CSS pur.
- **Préférence utilisateur déjà actée** : tout travail UI passe par le skill `design-taste-frontend` en **mode preserve** (on respecte et on élève le langage visuel existant, on ne le remplace pas).

**Inspiration Efferd retenue** (patterns structurels, pas de copie) : grille de KPI cards denses avec label contextuel + valeur proéminente ; charts en zones secondaires sous les KPIs ; table de transactions (texte aligné à gauche, montants à droite) ; toolbar avec contrôle de période ; icônes type Lucide en renfort discret ; hiérarchie header → KPIs → charts → table.

### D-DASH-02 — Chart.js **lazy-loadé** (pas dans `index.html`)
**Décision** : Chart.js (~200 Ko) est **chargé dynamiquement depuis `dashboard.js`** (injection d'un `<script>` CDN une seule fois, awaité), **pas** ajouté globalement dans `index.html`.

**Justification** : le SDK Supabase est global car requis partout ; Chart.js n'est utile que sur `/dashboard`. Le lazy-load respecte la philosophie du router (pages lazy-loadées) et n'alourdit pas les 8 autres routes. Le CDN reste la source (zéro dépendance installée, conforme à l'esprit du projet). Fallback géré si le CDN échoue.

### D-DASH-03 — Écosystème Agent Skills
- Capacité `find-skills` (vercel-labs) installée pour la découverte de skills.
- Skill **`supabase/agent-skills@supabase-postgres-best-practices`** (source officielle Supabase, 202K installs, Snyk *Low Risk*) installé et **appliqué à la migration** : RLS `(select auth.uid())` (évalué une fois → ~100× plus rapide que `auth.uid()` par ligne), indexation systématique des colonnes FK, contraintes `check`.
- Skills « dashboard » tiers trouvés (`grafana`, `kpi-dashboard-design`…) **écartés** : inadaptés au stack Vanilla + Chart.js, sources à confiance plus faible.

---

## Fonctionnalités attendues

### Saisie de données (formulaire — modal)
- Ajouter une transaction : type (`achat` | `vente`), article (texte libre), montant (€), date, et optionnellement un lien vers l'annonce
- Lier optionnellement une transaction à une recherche existante (`search_id`)
- Modifier ou supprimer une transaction existante

### Graphiques
- **Courbe temporelle** : achats vs ventes cumulés par mois
- **Barres** : profit mensuel net (ventes − achats)
- **KPIs** en haut : total investi, total encaissé, profit net global, ROI %

### Scope
- Données strictement privées : chaque user ne voit que ses propres transactions (RLS)
- Pas de vue agrégée inter-utilisateurs
- Librairie graphique : Chart.js (CDN, lazy-load — cf. D-DASH-02)

---

## Schéma DB à ajouter (migration Supabase)

Fichier : `supabase/migrations/2026-06-01-transactions.sql` — **durci selon `supabase-postgres-best-practices`** :

```sql
create table if not exists public.transactions (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references auth.users(id) on delete cascade,
  type        text not null check (type in ('achat','vente')),
  label       text not null check (char_length(label) between 1 and 200),
  amount      numeric(10,2) not null check (amount > 0),
  date        date not null default current_date,
  search_id   uuid references public.searches(id) on delete set null,
  url         text,
  created_at  timestamptz not null default now()
);

-- Index FK + index composite pour la requête type (mes transactions, triées par date)
create index if not exists transactions_user_date_idx on public.transactions (user_id, date desc);
create index if not exists transactions_search_id_idx on public.transactions (search_id);

alter table public.transactions enable row level security;

-- Policies granulaires par opération, auth.uid() wrappé dans (select ...) pour la perf
drop policy if exists "transactions_select_own" on public.transactions;
create policy "transactions_select_own" on public.transactions
  for select to authenticated using ((select auth.uid()) = user_id);

drop policy if exists "transactions_insert_own" on public.transactions;
create policy "transactions_insert_own" on public.transactions
  for insert to authenticated with check ((select auth.uid()) = user_id);

drop policy if exists "transactions_update_own" on public.transactions;
create policy "transactions_update_own" on public.transactions
  for update to authenticated
  using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);

drop policy if exists "transactions_delete_own" on public.transactions;
create policy "transactions_delete_own" on public.transactions
  for delete to authenticated using ((select auth.uid()) = user_id);
```

---

## Fichiers à créer / modifier

| Fichier | Action |
|---|---|
| `supabase/migrations/2026-06-01-transactions.sql` | Créer (migration durcie) |
| `js/pages/dashboard.js` | Créer (page SPA + lazy-load Chart.js + CRUD + charts) |
| `js/lib/transactions.js` | Créer (couche d'accès DB : list/create/update/delete) |
| `style.css` | Ajouter le bloc `/* ===== DASHBOARD ===== */` (KPI cards, charts, table, modal réutilisé) |
| `js/main.js` | Ajouter la route `/dashboard` |
| `js/components/header.js` | Ajouter le lien nav « 📊 Dashboard » |
| `index.html` | **Inchangé** (Chart.js lazy-loadé depuis dashboard.js — cf. D-DASH-02) |

---

## Contraintes techniques (révisées)

- Respecter l'architecture SPA (lazy-load dans `main.js`, `requireAuth()` + garde `navState.token` en tête de page)
- **Zéro dépendance npm, zéro build step** (maintenu — cf. D-DASH-01)
- Chart.js via CDN, **lazy-loadé** (cf. D-DASH-02)
- `server.py` non impacté
- RLS stricte : `(select auth.uid()) = user_id` sur toutes les opérations
- UI cohérente avec le dark theme existant — composants réutilisés (`.card`, `.stat-*`, `.btn-*`, `.modal-*`, `.empty-state`)
- Réutiliser les patterns anti-bug connus (garde `navState.token` avant chaque écriture DOM, pas de `getProfile(true)`)

---

## UX / Maquette indicative

```
┌──────────────────────────────────────────────────────────┐
│  📊 Tableau de bord financier              [+ Ajouter]    │
│                                                            │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐      │
│  │💰 Investi│ │💵Encaissé│ │📈 Profit │ │🎯  ROI   │      │
│  │  350 €   │ │  520 €   │ │ +170 €   │ │ +48,6 %  │      │
│  │ 4 achats │ │ 3 ventes │ │ net      │ │          │      │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘      │
│                                                            │
│  ┌───────────────────────┐ ┌───────────────────────┐      │
│  │ Achats vs ventes (cumul)│ │ Profit net mensuel    │      │
│  │ [courbe ───────────]  │ │ [barres ▇ ▅ ▇ ▂]      │      │
│  └───────────────────────┘ └───────────────────────┘      │
│                                                            │
│  Historique des transactions                               │
│  ┌────────────────────────────────────────────────────┐  │
│  │ 01/06  [vente]  Vélo VTT          120 €      ✏️ 🗑  │  │
│  │ 28/05  [achat]  Vélo VTT           80 €      ✏️ 🗑  │  │
│  └────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

---

## Ordre d'implémentation

1. ✅ Mettre à jour ce plan (source de vérité)
2. **Migration SQL** — `supabase/migrations/2026-06-01-transactions.sql` (durcie) + appliquer dans le Dashboard Supabase
3. **`js/lib/transactions.js`** — couche d'accès (list/create/update/delete, agrégats)
4. **`js/pages/dashboard.js`** — squelette + `requireAuth()` + fetch + KPIs + table historique
5. **Charts** — lazy-load Chart.js, courbe cumul achats/ventes + barres profit mensuel (thème dark)
6. **Formulaire** — modal ajout / édition / suppression
7. **Route + nav** — `/dashboard` dans `main.js` + lien header
8. **CSS** — bloc dashboard dans `style.css`
9. **Tests** — manuels (CRUD, KPIs, charts, RLS) + non-régression routes existantes

---

## Critères de validation (Definition of Done)

- [ ] Migration appliquée sur Supabase (table `transactions` + RLS visibles)
- [ ] Route `/dashboard` accessible depuis le header (users loggés)
- [ ] Formulaire : ajout, édition, suppression fonctionnels
- [ ] KPIs corrects (vérif manuelle)
- [ ] Courbe temporelle + barres profit mensuel s'affichent avec données réelles
- [ ] Chart.js lazy-loadé (pas chargé sur les autres routes) + fallback si CDN KO
- [ ] RLS vérifié : un user ne lit/écrit pas les transactions d'un autre
- [ ] Zéro régression sur `/hub`, `/scraper`, `/search/:id`, `/admin`, etc.
- [ ] Aucune dépendance npm / build step ajouté
