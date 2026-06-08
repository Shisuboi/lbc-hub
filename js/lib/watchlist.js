// js/lib/watchlist.js
// Accès aux recherches surveillées (watchlist_searches) + télémétrie (scrape_heartbeats).
// "Une seule active à la fois" passe par la RPC set_active_watchlist (atomique).
import { supa } from '../supabase-client.js';

const SELECT = 'id, owner_id, title, source_url, platform, price_max, price_min, exclude_keywords, ' +
  'min_margin_eur, min_margin_pct, active, created_at, author:profiles(username, avatar_color)';

/** Déduit la plateforme depuis l'URL (badge + colonne platform). */
export function deducePlatform(url) {
  const u = (url || '').toLowerCase();
  if (u.includes('leboncoin.')) return 'leboncoin';
  if (u.includes('ebay.')) return 'ebay';
  if (u.includes('vinted.')) return 'vinted';
  return 'other';
}

/** Toutes les recherches surveillées, plus récente d'abord. */
export async function listSearches() {
  const { data, error } = await supa
    .from('watchlist_searches')
    .select(SELECT)
    .order('created_at', { ascending: false });
  if (error) throw new Error('Chargement des recherches impossible : ' + error.message);
  return data || [];
}

/** Crée une recherche (owner_id = moi). */
export async function createSearch(ownerId, { title, source_url, price_max, price_min, exclude_keywords }) {
  const t = (title || '').trim();
  const url = (source_url || '').trim();
  if (!t) throw new Error('Titre requis.');
  if (!url) throw new Error('URL de recherche requise.');
  const row = {
    owner_id: ownerId,
    title: t,
    source_url: url,
    platform: deducePlatform(url),
    price_max: price_max != null && price_max !== '' ? Number(price_max) : null,
    price_min: price_min != null && price_min !== '' ? Number(price_min) : null,
    exclude_keywords: (exclude_keywords || '').trim(),
    active: false, // on n'active jamais à la création (l'utilisateur clique "Activer")
  };
  const { data, error } = await supa
    .from('watchlist_searches').insert(row).select(SELECT).single();
  if (error) throw new Error('Création impossible : ' + error.message);
  return data;
}

/** Édite une recherche (sienne, ou n'importe laquelle si admin via RLS). */
export async function updateSearch(id, fields) {
  const patch = {};
  if (fields.title != null) patch.title = String(fields.title).trim();
  if (fields.source_url != null) {
    patch.source_url = String(fields.source_url).trim();
    patch.platform = deducePlatform(patch.source_url);
  }
  if (fields.price_max !== undefined)
    patch.price_max = fields.price_max === '' || fields.price_max == null ? null : Number(fields.price_max);
  if (fields.price_min !== undefined)
    patch.price_min = fields.price_min === '' || fields.price_min == null ? null : Number(fields.price_min);
  if (fields.exclude_keywords != null) patch.exclude_keywords = String(fields.exclude_keywords).trim();
  const { data, error } = await supa
    .from('watchlist_searches').update(patch).eq('id', id).select(SELECT).single();
  if (error) throw new Error('Modification impossible : ' + error.message);
  return data;
}

/** Supprime une recherche (sienne, ou n'importe laquelle si admin). */
export async function deleteSearch(id) {
  const { error } = await supa.from('watchlist_searches').delete().eq('id', id);
  if (error) throw new Error('Suppression impossible : ' + error.message);
}

/** Active CETTE recherche et met toutes les autres en pause (RPC atomique). */
export async function setActive(searchId) {
  const { error } = await supa.rpc('set_active_watchlist', { p_search_id: searchId });
  if (error) throw new Error('Activation impossible : ' + error.message);
}

/** Met une recherche en pause (active=false sur la sienne via RLS update-own). */
export async function pauseSearch(id) {
  const { error } = await supa.from('watchlist_searches').update({ active: false }).eq('id', id);
  if (error) throw new Error('Mise en pause impossible : ' + error.message);
}

/** Télémétrie : Map<search_id, heartbeat-row>. */
export async function getHeartbeats() {
  const map = new Map();
  const { data, error } = await supa.from('scrape_heartbeats').select('*');
  if (error || !data) return map; // best-effort : on n'empêche pas la gestion
  for (const row of data) map.set(row.search_id, row);
  return map;
}

/** Abonnement realtime à scrape_heartbeats. onChange() sur tout INSERT/UPDATE/DELETE.
 * Nom de canal UNIQUE par souscription : si on revient sur /watchlist avant que
 * l'ancien canal soit retiré (nettoyage via timer), un nom fixe ferait réutiliser
 * un canal déjà subscribe() → erreur "cannot add postgres_changes after subscribe()".
 * Renvoie le canal (à passer à supa.removeChannel au démontage). */
export function subscribeHeartbeats(onChange) {
  return supa
    .channel('scrape-heartbeats-' + Math.random().toString(36).slice(2))
    .on('postgres_changes',
      { event: '*', schema: 'public', table: 'scrape_heartbeats' },
      () => onChange())
    .subscribe();
}
