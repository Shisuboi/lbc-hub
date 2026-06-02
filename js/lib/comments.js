// js/lib/comments.js
// Accès aux commentaires par item (table item_comments, RLS).
// L'auteur est récupéré par jointure (FK user_id -> profiles).
import { supa } from '../supabase-client.js';

const SELECT = 'id, opportunity_id, user_id, body, edited_at, created_at, author:profiles(username, avatar_color)';

/** Liste les commentaires d'une opportunité, du plus ancien au plus récent. */
export async function listComments(opportunityId) {
  const { data, error } = await supa
    .from('item_comments')
    .select(SELECT)
    .eq('opportunity_id', opportunityId)
    .order('created_at', { ascending: true });
  if (error) throw new Error('Chargement des commentaires impossible : ' + error.message);
  return data || [];
}

/** Poste un commentaire. Renvoie la ligne créée (avec auteur). */
export async function createComment(opportunityId, userId, body) {
  const text = (body || '').trim();
  if (!text) throw new Error('Commentaire vide.');
  if (text.length > 2000) throw new Error('Commentaire trop long (max 2000 caractères).');
  const { data, error } = await supa
    .from('item_comments')
    .insert({ opportunity_id: opportunityId, user_id: userId, body: text })
    .select(SELECT)
    .single();
  if (error) throw new Error('Publication impossible : ' + error.message);
  return data;
}

/** Édite son commentaire (renseigne edited_at). */
export async function updateComment(id, body) {
  const text = (body || '').trim();
  if (!text) throw new Error('Commentaire vide.');
  if (text.length > 2000) throw new Error('Commentaire trop long (max 2000 caractères).');
  const { data, error } = await supa
    .from('item_comments')
    .update({ body: text, edited_at: new Date().toISOString() })
    .eq('id', id)
    .select(SELECT)
    .single();
  if (error) throw new Error('Modification impossible : ' + error.message);
  return data;
}

/** Supprime un commentaire (RLS : le sien, ou n'importe lequel si admin). */
export async function deleteComment(id) {
  const { error } = await supa.from('item_comments').delete().eq('id', id);
  if (error) throw new Error('Suppression impossible : ' + error.message);
}

/** Compte les commentaires pour une liste d'opportunités. Renvoie Map<oppId, n>.
 * Tally côté client (une seule requête) : suffisant à l'échelle du projet, pas de vue/RPC. */
export async function loadCommentCounts(oppIds = []) {
  const counts = new Map();
  if (!oppIds.length) return counts;
  const { data, error } = await supa
    .from('item_comments')
    .select('opportunity_id')
    .in('opportunity_id', oppIds);
  if (error || !data) return counts; // compteur best-effort : on ne casse pas le feed
  for (const row of data) {
    counts.set(row.opportunity_id, (counts.get(row.opportunity_id) || 0) + 1);
  }
  return counts;
}

/** Souscrit aux changements realtime des commentaires d'un item.
 * onChange() est appelé sur tout INSERT/UPDATE/DELETE concernant cette opportunité.
 * Renvoie le canal (à passer à supa.removeChannel au démontage). */
export function subscribeComments(opportunityId, onChange) {
  return supa
    .channel('item-comments-' + opportunityId)
    .on('postgres_changes',
      { event: '*', schema: 'public', table: 'item_comments', filter: `opportunity_id=eq.${opportunityId}` },
      () => onChange())
    .subscribe();
}
