// js/lib/item-favorites.js
// Favoris sur opportunité (table item_favorites). Set en mémoire, mises à jour optimistes.
import { supa } from '../supabase-client.js';

let favSet = new Set();

export function isFav(id) { return favSet.has(id); }
export function favorites() { return favSet; }

/** Charge les favoris du user courant dans le Set mémoire. */
export async function loadFavorites(userId) {
  favSet = new Set();
  if (!userId) return favSet;
  const { data, error } = await supa
    .from('item_favorites').select('opportunity_id').eq('user_id', userId);
  if (!error && data) favSet = new Set(data.map(r => r.opportunity_id));
  return favSet;
}

/** Bascule un favori (optimiste, rollback si la DB échoue). */
export async function toggleFavorite(userId, oppId) {
  if (!userId) throw new Error('Non authentifié.');
  if (favSet.has(oppId)) {
    favSet.delete(oppId);
    const { error } = await supa.from('item_favorites')
      .delete().eq('user_id', userId).eq('opportunity_id', oppId);
    if (error) { favSet.add(oppId); throw error; }
  } else {
    favSet.add(oppId);
    const { error } = await supa.from('item_favorites')
      .insert({ user_id: userId, opportunity_id: oppId });
    if (error) { favSet.delete(oppId); throw error; }
  }
}
