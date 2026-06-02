# Phase C-4 — Notif sur réponse (badge « nouveau » sur le feed)

> Date : 2026-06-02
> Étend la spec Phase C (`2026-06-01-phase-c-hub-opportunites-design.md` §164, sous-phase C-4).
> Statut : design validé, à implémenter.

## 1. Objectif

Signaler sur le feed les items où **j'ai participé** (au moins un commentaire de moi) **et** qui ont
reçu un **commentaire plus récent que ma dernière visite**. Pas de threading réel : `item_comments`
est un fil plat (pas de `parent_id`), donc « réponse » = **nouveau commentaire sur un fil où j'ai
participé**.

Niveau retenu (cadrage) : **badge in-app sur le feed uniquement** (pas de notification système, pas
de compteur global header). Approche la plus légère de la spec.

## 2. Mécanisme — `localStorage` (pas de base)

Choisi parmi 2 options :
- **`localStorage` (retenu)** : on mémorise par item l'horodatage du dernier commentaire vu. Zéro
  table, zéro migration, zéro requête serveur supplémentaire. Limite assumée : le « vu » est par
  navigateur (changer d'appareil peut refaire apparaître un item « nouveau » une fois).
- **Table `comment_reads` (écartée)** : suivi serveur synchronisé multi-appareils, mais nouvelle
  table + RLS + migration + requêtes → sur-ingénierie pour un groupe d'amis. La spec Phase C l'écarte
  explicitement.

## 3. Composants

### `js/lib/comment-seen.js` (nouveau)

Une map `localStorage` sous une clé unique (ex. `lbc-comment-seen`), `{ [opportunityId]: dernierISOvu }`.

- `markSeen(opportunityId, iso)` — enregistre `iso` comme dernier commentaire vu pour cet item
  (n'écrit que si `iso` est plus récent que la valeur stockée).
- `isUnseen(opportunityId, latestIso)` — `true` si `latestIso` existe et est strictement plus récent
  que le « vu » stocké (ou si rien n'est stocké mais qu'il y a un `latestIso`).

Best-effort : tout accès `localStorage` est encapsulé en try/catch (mode privé / quota) et dégrade en
« pas de badge » plutôt que de casser le feed.

### Chargement du feed — 1 seule requête (étendue)

Aujourd'hui, `loadCommentCounts(oppIds)` (`js/lib/comments.js`) fait **une** requête
`select opportunity_id from item_comments where opportunity_id in (...)` et compte côté client.

On remplace/complète par une fonction qui ramène aussi `user_id` et `created_at` pour les items
visibles, et calcule par item :
- `count` (comme aujourd'hui, pour le 💬 N) ;
- `participated` (existe un commentaire au `user_id` courant) ;
- `latest` (max des `created_at`).

→ **Toujours une seule requête**, pas de surcoût réseau. Le badge « nouveau » d'un item =
`participated && isUnseen(opportunityId, latest)`.

### Rendu — `js/components/opportunity-row.js`

Quand un item est marqué « nouveau », ajouter un indicateur discret sur le compteur de commentaires
(ex. un point/halo : `💬 3 ●`). Aucun changement de layout majeur, dans la continuité de la DA.

### Clear du badge — page item

Sur `/item/:id` (`js/pages/item.js` / `js/components/comments.js`), au chargement des commentaires
**et** à chaque mise à jour temps réel pendant qu'on regarde la page, appeler
`markSeen(opportunityId, dernierCreatedAt)`. Ouvrir l'item (ou y poster un commentaire) éteint donc le
badge à la prochaine vue du feed.

## 4. Cas limites (assumés)

- **Mon propre nouveau commentaire ne me notifie pas** : la page item marque « vu » au chargement et
  à chaque update, donc poster met à jour le « vu ».
- **Seuls les items visibles dans le feed sont évalués** : le badge est une aide au coup d'œil, pas un
  compteur global exhaustif.
- **Multi-appareils** : « vu » par navigateur (cf. §2). Acceptable.
- **`localStorage` indisponible** : dégradation silencieuse (pas de badge), le feed fonctionne.

## 5. Tests

Convention projet : pas de tests frontend automatisés. Validation manuelle (check-list) :
1. User A commente l'item X. User B commente aussi X. Depuis A : sur `/feed`, X montre le badge
   « nouveau ».
2. A ouvre X → le fil s'affiche ; retour `/feed` → le badge a disparu.
3. A poste un commentaire sur X → pas de badge pour A.
4. Un item où A n'a jamais commenté ne montre jamais de badge, même s'il a des commentaires.
5. Console F12 propre ; le compteur 💬 N reste correct (non-régression C-2).

## 6. Hors scope

- Notification système (Notification API) et compteur global header (écartés au cadrage — possibles
  plus tard en réutilisant le toggle de l'ancien hub).
- Threading / réponses ciblées (pas de `parent_id` ; hors scope).
- Suivi « vu » synchronisé multi-appareils (table serveur — écarté).
