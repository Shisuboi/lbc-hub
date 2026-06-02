// js/components/comments.js
// Fil de commentaires d'un item : rendu, saisie, édition, suppression, temps réel.
// Monté par js/pages/item.js dans un conteneur fourni. Gère son propre canal realtime
// via window.__commentsChannel (démonté au montage suivant — pattern feed/hub).
import { supa } from '../supabase-client.js';
import { listComments, createComment, updateComment, deleteComment, subscribeComments } from '../lib/comments.js';
import { markSeen } from '../lib/comment-seen.js';

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
function timeAgo(iso) {
  const d = new Date(iso), s = (Date.now() - d.getTime()) / 1000;
  if (s < 60) return "à l'instant";
  if (s < 3600) return `il y a ${Math.floor(s / 60)} min`;
  if (s < 86400) return `il y a ${Math.floor(s / 3600)} h`;
  return d.toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' });
}
function avatar(c) {
  const name = c.author?.username || '?';
  const color = c.author?.avatar_color || 'var(--c-acc)';
  return `<span class="cm-avatar" style="background:${esc(color)}">${esc(name[0].toUpperCase())}</span>`;
}

/**
 * Monte le fil de commentaires.
 * @param {HTMLElement} container  conteneur cible (vidé puis rempli)
 * @param {object} opts  { opportunityId, me }  me = profil courant { id, username, role }
 */
export async function mountComments(container, { opportunityId, me }) {
  // Démonte un éventuel canal d'un item précédent
  if (window.__commentsChannel) {
    try { await supa.removeChannel(window.__commentsChannel); } catch (_) {}
    window.__commentsChannel = null;
  }

  let comments = [];
  const isAdmin = me?.role === 'admin';

  container.innerHTML = `
    <section class="cm-section">
      <h3 class="cm-title">💬 Commentaires <span id="cmCount" class="cm-count"></span></h3>
      <div id="cmList" class="cm-list"><div class="muted">Chargement…</div></div>
      <form id="cmForm" class="cm-form">
        <textarea id="cmInput" class="cm-input" rows="2" maxlength="2000"
          placeholder="Ajouter un commentaire…"></textarea>
        <button type="submit" class="btn-acc">Publier</button>
      </form>
    </section>`;

  const listEl = container.querySelector('#cmList');
  const countEl = container.querySelector('#cmCount');
  const form = container.querySelector('#cmForm');
  const input = container.querySelector('#cmInput');

  function canDelete(c) { return c.user_id === me?.id || isAdmin; }
  function canEdit(c)   { return c.user_id === me?.id; }

  function rowHtml(c) {
    const edited = c.edited_at ? ' <span class="cm-edited">(modifié)</span>' : '';
    const actions = `
      ${canEdit(c)   ? `<button class="cm-link" data-edit="${c.id}">Modifier</button>` : ''}
      ${canDelete(c) ? `<button class="cm-link cm-danger" data-del="${c.id}">Supprimer</button>` : ''}`;
    return `
      <div class="cm-item" data-id="${c.id}">
        ${avatar(c)}
        <div class="cm-body">
          <div class="cm-head">
            <span class="cm-author">${esc(c.author?.username || 'Anonyme')}</span>
            <span class="cm-time">${timeAgo(c.created_at)}${edited}</span>
          </div>
          <div class="cm-text" data-text="${c.id}">${esc(c.body)}</div>
          <div class="cm-actions">${actions}</div>
        </div>
      </div>`;
  }

  function renderList() {
    if (!comments.length) {
      listEl.innerHTML = `<div class="cm-empty muted">Aucun commentaire. Soyez le premier !</div>`;
    } else {
      listEl.innerHTML = comments.map(rowHtml).join('');
    }
    countEl.textContent = comments.length ? `(${comments.length})` : '';
  }

  async function reload() {
    try {
      comments = await listComments(opportunityId);
      renderList();
      // Marque l'item comme "vu" jusqu'au dernier commentaire (éteint le badge du feed).
      // reload() tourne au montage, après post/édit/suppr, et à chaque update temps réel.
      if (comments.length) markSeen(opportunityId, comments[comments.length - 1].created_at);
    } catch (err) {
      listEl.innerHTML = `<div class="error-panel card">❌ ${esc(err.message)}</div>`;
    }
  }

  await reload();

  // Poster
  form.addEventListener('submit', async e => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text || !me?.id || form.dataset.pending) return;
    form.dataset.pending = '1';
    try {
      await createComment(opportunityId, me.id, text);
      input.value = '';
      await reload();                 // le realtime rafraîchira aussi les autres clients
    } catch (err) {
      alert(err.message);
    } finally { delete form.dataset.pending; }
  });

  // Édition / suppression (délégation)
  listEl.addEventListener('click', async e => {
    const delBtn = e.target.closest('[data-del]');
    const editBtn = e.target.closest('[data-edit]');

    if (delBtn) {
      const id = delBtn.dataset.del;
      if (!confirm('Supprimer ce commentaire ?')) return;
      try { await deleteComment(id); await reload(); }
      catch (err) { alert(err.message); }
      return;
    }

    if (editBtn) {
      const id = editBtn.dataset.edit;
      const c = comments.find(x => x.id === id);
      if (!c) return;
      const textEl = listEl.querySelector(`[data-text="${id}"]`);
      // Transforme la ligne en mini-éditeur inline
      textEl.innerHTML = `
        <textarea class="cm-input cm-edit-input" rows="2" maxlength="2000">${esc(c.body)}</textarea>
        <div class="cm-edit-actions">
          <button class="btn-acc cm-save" data-save="${id}">Enregistrer</button>
          <button class="cm-link cm-cancel">Annuler</button>
        </div>`;
      const ta = textEl.querySelector('textarea');
      ta.focus();
      textEl.querySelector('.cm-cancel').addEventListener('click', renderList);
      textEl.querySelector('.cm-save').addEventListener('click', async () => {
        const nv = ta.value.trim();
        if (!nv) return;
        try { await updateComment(id, nv); await reload(); }
        catch (err) { alert(err.message); }
      });
    }
  });

  // Realtime : tout changement sur cet item recharge le fil
  window.__commentsChannel = subscribeComments(opportunityId, () => reload());
}
