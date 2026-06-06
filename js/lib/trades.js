// js/lib/trades.js
// Couche d'accès au Journal de trading PARTAGÉ (table trades).
// Lecture : tous les membres. Écriture : auteur ou admin (garanti par la RLS).
// L'auteur est joint depuis profiles (username, avatar_color).
import { supa, getCachedSession } from '../supabase-client.js';

const SELECT =
  'id, user_id, opportunity_id, title, status, buy_price, sell_price, ' +
  'bought_at, sold_at, notes, created_at, updated_at, ' +
  'author:profiles(username, avatar_color)';

/** Tous les deals du groupe, du plus récemment modifié au plus ancien. */
export async function listTrades() {
  const { data, error } = await supa
    .from('trades')
    .select(SELECT)
    .order('updated_at', { ascending: false });
  if (error) throw new Error('Chargement du journal impossible : ' + error.message);
  return data || [];
}

// Construit la ligne à écrire à partir des champs du formulaire (normalise les null).
function buildRow(input) {
  const status = input.status || 'contacted';
  const num = v => (v === '' || v == null || isNaN(Number(v))) ? null : Number(v);
  return {
    title: String(input.title || '').trim().slice(0, 200),
    status,
    opportunity_id: input.opportunity_id || null,
    buy_price: status === 'contacted' ? null : num(input.buy_price),
    sell_price: status === 'sold' ? num(input.sell_price) : null,
    bought_at: status === 'contacted' ? null : (input.bought_at || null),
    sold_at: status === 'sold' ? (input.sold_at || null) : null,
    notes: input.notes?.trim() || null,
  };
}

/** Crée un deal (user_id = moi). Renvoie la ligne créée (avec auteur). */
export async function createTrade(input) {
  const session = await getCachedSession();
  const user = session?.user;
  if (!user) throw new Error('Non authentifié. Reconnecte-toi.');
  const row = { user_id: user.id, ...buildRow(input) };
  const { data, error } = await supa.from('trades').insert(row).select(SELECT).single();
  if (error) throw new Error('Création impossible : ' + error.message);
  return data;
}

/** Met à jour un deal (RLS : auteur ou admin). */
export async function updateTrade(id, input) {
  const { data, error } = await supa
    .from('trades').update(buildRow(input)).eq('id', id).select(SELECT).single();
  if (error) throw new Error('Mise à jour impossible : ' + error.message);
  return data;
}

/** Supprime un deal (RLS : auteur ou admin). */
export async function deleteTrade(id) {
  const { error } = await supa.from('trades').delete().eq('id', id);
  if (error) throw new Error('Suppression impossible : ' + error.message);
}

/** Recherche d'opportunités du feed pour lier un deal. Best-effort (renvoie [] si erreur). */
export async function searchOpportunities(query) {
  const q = (query || '').trim();
  if (q.length < 2) return [];
  const { data, error } = await supa
    .from('opportunities')
    .select('id, title, price, category')
    .ilike('title', `%${q}%`)
    .order('created_at', { ascending: false })
    .limit(8);
  if (error || !data) return [];
  return data;
}

/** KPIs du groupe — profit RÉALISÉ (deals revendus uniquement). */
export function computeGroupKpis(trades) {
  let invested = 0, earned = 0, contacted = 0, bought = 0, sold = 0;
  for (const t of trades) {
    if (t.status === 'contacted') contacted++;
    else if (t.status === 'bought') bought++;
    else if (t.status === 'sold') {
      sold++;
      invested += Number(t.buy_price || 0);
      earned += Number(t.sell_price || 0);
    }
  }
  const profit = earned - invested;
  const roi = invested > 0 ? (profit / invested) * 100 : null;
  return { invested, earned, profit, roi, counts: { contacted, bought, sold } };
}

const MONTH_FR = ['janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin',
  'juil.', 'août', 'sept.', 'oct.', 'nov.', 'déc.'];

/** Clé 'YYYY-MM' d'une date ISO. */
function monthKey(iso) { return iso ? iso.slice(0, 7) : null; }

/** Libellé court d'une clé mensuelle 'YYYY-MM' → "janv. 25". */
export function formatMonthLabel(key) {
  const [y, m] = key.split('-');
  return `${MONTH_FR[Number(m) - 1]} ${y.slice(2)}`;
}

/** Classement des membres par profit net réalisé (deals sold uniquement). */
export function computeLeaderboard(trades) {
  const map = new Map();
  for (const t of trades) {
    if (t.status !== 'sold') continue;
    const uid = t.user_id;
    if (!map.has(uid)) {
      map.set(uid, {
        user_id: uid,
        username: t.author?.username || 'Anonyme',
        avatar_color: t.author?.avatar_color || 'var(--accent)',
        invested: 0, earned: 0, soldCount: 0,
      });
    }
    const m = map.get(uid);
    m.invested += Number(t.buy_price || 0);
    m.earned   += Number(t.sell_price || 0);
    m.soldCount++;
  }
  return [...map.values()]
    .map(m => ({
      ...m,
      profit: m.earned - m.invested,
      roi: m.invested > 0 ? (m.earned - m.invested) / m.invested * 100 : null,
    }))
    .sort((a, b) => b.profit - a.profit || b.soldCount - a.soldCount);
}

/** Séries mensuelles pour les graphes : cumul achats/ventes + profit mensuel réalisé. */
export function buildMonthlySeries(trades) {
  const buysByMonth = new Map(), sellsByMonth = new Map();
  for (const t of trades) {
    if (t.buy_price != null && t.bought_at) {
      const k = monthKey(t.bought_at);
      buysByMonth.set(k, (buysByMonth.get(k) || 0) + Number(t.buy_price));
    }
    if (t.status === 'sold' && t.sell_price != null && t.sold_at) {
      const k = monthKey(t.sold_at);
      sellsByMonth.set(k, (sellsByMonth.get(k) || 0) + Number(t.sell_price));
    }
  }
  const labels = [...new Set([...buysByMonth.keys(), ...sellsByMonth.keys()])].sort();
  let cb = 0, cs = 0;
  const buysCumul = [], sellsCumul = [], profitMonthly = [];
  for (const k of labels) {
    const b = buysByMonth.get(k) || 0, s = sellsByMonth.get(k) || 0;
    cb += b; cs += s;
    buysCumul.push(cb); sellsCumul.push(cs); profitMonthly.push(s - b);
  }
  return { labels, buysCumul, sellsCumul, profitMonthly };
}
