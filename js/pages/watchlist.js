// js/pages/watchlist.js
// Page /watchlist : panneau LIVE (ce que le PC scrape : état, annonces/min, dernière passe, cumul)
// + gestion des recherches (ajout / activer (1 seule) / pause / éditer / supprimer).
import { requireAuth, getProfile } from '../auth.js';
import { navState } from '../router.js';
import { supa } from '../supabase-client.js';
import {
  listSearches, createSearch, updateSearch, deleteSearch,
  setActive, pauseSearch, getHeartbeats, subscribeHeartbeats,
} from '../lib/watchlist.js';

const ONLINE_THRESHOLD_S = 45; // au-delà → PC considéré hors ligne
const PLATFORM_BADGE = { leboncoin: '🟠', ebay: '🔵', vinted: '🟢', other: '⚪' };

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
function ago(seconds) {
  if (seconds < 60) return `il y a ${Math.max(0, Math.round(seconds))} s`;
  if (seconds < 3600) return `il y a ${Math.round(seconds / 60)} min`;
  return `il y a ${Math.round(seconds / 3600)} h`;
}

export async function render() {
  const myToken = navState.token;
  await requireAuth();
  if (navState.token !== myToken) return;
  const me = await getProfile();
  if (navState.token !== myToken) return;

  const root = document.getElementById('appRoot');
  root.innerHTML = `
    <section class="feed-page">
      <p class="feed-eyebrow">Monitoring · ce que le PC scrape en continu</p>
      <div id="wlLive"></div>
      <h3 class="wl-section-title">📡 Mes recherches</h3>
      <div id="wlList"><div class="page-loading">⏳ Chargement…</div></div>
      <div id="wlAdd"></div>
    </section>`;

  let searches = [];
  let beats = new Map();

  async function reload() {
    [searches, beats] = await Promise.all([listSearches(), getHeartbeats()]);
    if (navState.token !== myToken) return;
    paintLive();
    paintList();
  }

  // ---- Panneau LIVE (recherche active) ----
  function paintLive() {
    const el = document.getElementById('wlLive');
    if (!el) return;
    const active = searches.find(s => s.active);
    if (!active) {
      el.innerHTML = `<div class="wl-live wl-hero glass-panel wl-live-idle">😴 Aucune recherche active. Active-en une ci-dessous pour lancer le PC.</div>`;
      return;
    }
    const hb = beats.get(active.id);
    const lastBeat = hb && hb.heartbeat_at ? new Date(hb.heartbeat_at).getTime() : null;
    const elapsed = lastBeat != null ? (Date.now() - lastBeat) / 1000 : Infinity;
    const online = elapsed <= ONLINE_THRESHOLD_S;
    const stateHtml = online
      ? `<span class="wl-dot wl-on"></span> PC actif (${ago(elapsed)})`
      : `<span class="wl-dot wl-off"></span> PC hors ligne${lastBeat != null ? ` (${ago(elapsed)})` : ''}`;
    const rate = hb && hb.new_ads_per_min != null ? hb.new_ads_per_min : 0;
    const lastPass = hb && hb.last_pass_at ? ago((Date.now() - new Date(hb.last_pass_at).getTime()) / 1000) : '—';
    const seen = hb && hb.ads_seen_total != null ? hb.ads_seen_total : 0;
    const blocked = hb && hb.blocked_recent != null ? hb.blocked_recent : 0;
    const quotaPaused = hb && hb.enrichment_paused === true;
    el.innerHTML = `
      <div class="wl-live wl-hero liquid is-live">
        <div class="wl-live-head">
          <div class="wl-live-title">${PLATFORM_BADGE[active.platform] || '⚪'} ${esc(active.title)}</div>
          <div class="wl-state ${online ? 'on' : 'off'}">${stateHtml}</div>
        </div>
        <div class="wl-live-by">par @${esc(active.author?.username || '?')}
          ${active.source_url ? `· <a href="${esc(active.source_url)}" target="_blank" rel="noopener noreferrer">voir la recherche ↗</a>` : ''}</div>
        ${quotaPaused ? `<div class="wl-quota-warn">⚠️ Quotas IA Gemini épuisés pour aujourd'hui — le scraping continue mais l'analyse IA reprendra demain.</div>` : ''}
        <div class="wl-metrics">
          <div class="wl-metric"><div class="wl-mval">${rate}</div><div class="wl-mlabel">annonces / min</div></div>
          <div class="wl-metric"><div class="wl-mval">${lastPass}</div><div class="wl-mlabel">dernière passe</div></div>
          <div class="wl-metric"><div class="wl-mval">${seen}</div><div class="wl-mlabel">annonces vues</div></div>
          <div class="wl-metric"><div class="wl-mval">${blocked}</div><div class="wl-mlabel">blocages récents</div></div>
        </div>
      </div>`;
  }

  // ---- Liste de gestion ----
  function paintList() {
    const el = document.getElementById('wlList');
    if (!el) return;
    if (!searches.length) {
      el.innerHTML = `<div class="card" style="padding:18px;text-align:center;color:var(--c-mut)">Aucune recherche pour l'instant. Ajoute-en une ci-dessus.</div>`;
      return;
    }
    el.innerHTML = `<div class="wl-rows">${searches.map(s => {
      const mine = s.owner_id === me.id;
      const canEdit = mine || me.role === 'admin';
      return `<div class="wl-row card" data-id="${s.id}">
        <div class="wl-row-main">
          <div class="wl-row-title">${PLATFORM_BADGE[s.platform] || '⚪'} ${esc(s.title)}
            ${s.active ? '<span class="wl-tag wl-tag-on">✅ en cours</span>' : '<span class="wl-tag wl-tag-off">⏸️ en pause</span>'}</div>
          <div class="wl-row-by muted">par @${esc(s.author?.username || '?')}</div>
        </div>
        <div class="wl-row-actions">
          ${s.active
            ? (canEdit ? `<button class="btn-mini" data-act="pause" data-id="${s.id}">Mettre en pause</button>` : '')
            : `<button class="btn-mini btn-mini-go" data-act="activate" data-id="${s.id}">Activer</button>`}
          ${canEdit ? `<button class="btn-mini" data-act="edit" data-id="${s.id}">Éditer</button>
                       <button class="btn-mini btn-mini-del" data-act="delete" data-id="${s.id}">Supprimer</button>` : ''}
        </div>
      </div>`;
    }).join('')}</div>`;
  }

  // ---- Formulaire d'ajout ----
  function paintAdd() {
    const el = document.getElementById('wlAdd');
    if (!el) return;
    el.innerHTML = `
      <form id="wlForm" class="wl-add card">
        <div class="wl-add-title">➕ Ajouter une recherche</div>
        <input name="title" placeholder="Titre (ex. PS5 d'occasion)" required>
        <input name="source_url" placeholder="URL de recherche Leboncoin" required>
        <div class="wl-add-row">
          <input name="price_min" type="number" min="0" placeholder="Prix min (€, optionnel)">
          <input name="price_max" type="number" min="0" placeholder="Prix max (€, optionnel)">
        </div>
        <input name="exclude_keywords" placeholder="Mots exclus, séparés par des virgules (optionnel)">
        <div class="wl-add-foot">
          <button type="submit" class="btn btn-primary">Ajouter</button>
          <span id="wlAddMsg" class="muted"></span>
        </div>
      </form>`;
    document.getElementById('wlForm').addEventListener('submit', async (e) => {
      e.preventDefault();
      const f = e.target;
      const msg = document.getElementById('wlAddMsg');
      msg.textContent = '⏳ Ajout…';
      try {
        await createSearch(me.id, {
          title: f.title.value, source_url: f.source_url.value,
          price_min: f.price_min.value, price_max: f.price_max.value,
          exclude_keywords: f.exclude_keywords.value,
        });
        f.reset();
        msg.textContent = '✅ Ajoutée.';
        await reload();
      } catch (err) {
        msg.textContent = '❌ ' + err.message;
      }
    });
  }

  // ---- Actions de la liste (délégation) ----
  document.getElementById('wlList').addEventListener('click', async (e) => {
    const btn = e.target.closest('button[data-act]');
    if (!btn) return;
    const id = btn.dataset.id;
    const act = btn.dataset.act;
    btn.disabled = true;
    try {
      if (act === 'activate') await setActive(id);
      else if (act === 'pause') await pauseSearch(id);
      else if (act === 'delete') {
        if (!confirm('Supprimer cette recherche ?')) { btn.disabled = false; return; }
        await deleteSearch(id);
      } else if (act === 'edit') {
        const s = searches.find(x => x.id === id);
        const title = prompt('Titre :', s.title);
        if (title === null) { btn.disabled = false; return; }
        const url = prompt('URL de recherche :', s.source_url);
        if (url === null) { btn.disabled = false; return; }
        const minPriceStr = prompt('Prix minimum (€, vide pour aucun) :', s.price_min ?? '');
        if (minPriceStr === null) { btn.disabled = false; return; }
        const maxPriceStr = prompt('Prix maximum (€, vide pour aucun) :', s.price_max ?? '');
        if (maxPriceStr === null) { btn.disabled = false; return; }
        await updateSearch(id, { 
          title, 
          source_url: url,
          price_min: minPriceStr === '' ? null : minPriceStr,
          price_max: maxPriceStr === '' ? null : maxPriceStr
        });
      }
      await reload();
    } catch (err) {
      alert(err.message);
      btn.disabled = false;
    }
  });

  paintAdd();
  await reload();
  if (navState.token !== myToken) return;

  // ---- Temps réel + timer de fraîcheur (auto-nettoyés à la navigation) ----
  const channel = subscribeHeartbeats(async () => {
    if (navState.token !== myToken) return;
    beats = await getHeartbeats();
    if (navState.token === myToken) paintLive();
  });
  const timer = setInterval(() => {
    if (navState.token !== myToken) {        // on a quitté la page : on nettoie
      clearInterval(timer);
      try { supa.removeChannel(channel); } catch (_) {}
      return;
    }
    paintLive(); // recalcule "il y a X s" et bascule online→offline tout seul
  }, 5000);
}
