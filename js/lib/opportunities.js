// js/lib/opportunities.js
// Accès aux opportunités (lecture seule côté membre, RLS opp_select_all).
// + helpers purs de filtre/tri (sans réseau).
import { supa } from '../supabase-client.js';

const SELECT = [
  'id', 'ad_id', 'title', 'price', 'url', 'image_url',
  'location_city', 'location_postal', 'lat', 'lon', 'category', 'resale_score',
  'est_market_price', 'est_margin_eur', 'est_margin_pct', 'max_buy_price',
  'price_dropped', 'previous_price', 'explanation', 'signals',
  'source_search_id', 'scraped_at', 'created_at', 'status',
].join(', ');

/** Liste les opportunités actives, plus récentes d'abord. */
export async function listOpportunities({ limit = 100 } = {}) {
  const { data, error } = await supa
    .from('opportunities')
    .select(SELECT)
    .eq('status', 'active')
    .order('created_at', { ascending: false })
    .limit(limit);
  if (error) throw new Error('Chargement des opportunités impossible : ' + error.message);
  return data || [];
}

/** Récupère une opportunité par id. */
export async function getOpportunity(id) {
  const { data, error } = await supa.from('opportunities').select(SELECT).eq('id', id).single();
  if (error) throw new Error('Opportunité introuvable : ' + error.message);
  return data;
}

/** Filtre + tri purs (testable, sans réseau). favSet = Set d'ids favoris. */
export function filterAndSort(items, {
  category = 'all', favOnly = false, favSet = new Set(),
  text = '', source = 'all', sort = 'recent',
} = {}) {
  let list = items.slice();
  if (category !== 'all') list = list.filter(o => o.category === category);
  if (source !== 'all') list = list.filter(o => o.source_search_id === source);
  if (favOnly) list = list.filter(o => favSet.has(o.id));
  if (text) {
    const t = text.toLowerCase();
    list = list.filter(o => (o.title || '').toLowerCase().includes(t));
  }
  switch (sort) {
    case 'score':  list.sort((a, b) => (b.resale_score || 0) - (a.resale_score || 0)); break;
    case 'margin': list.sort((a, b) => (b.est_margin_eur || 0) - (a.est_margin_eur || 0)); break;
    default:       list.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
  }
  return list;
}
