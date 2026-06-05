// js/pages/dashboard.js
// Page /dashboard = JOURNAL DE TRADING PARTAGÉ.
// Héro (profit groupe) + KPIs + 2 graphiques + Kanban 3 colonnes (Contacté/Acheté/Revendu)
// + modal CRUD adaptatif au statut + recherche/liaison d'une annonce du feed.
// Données partagées (RLS) : tout le groupe voit tous les deals ; écriture auteur/admin.
import { requireAuth, getProfile } from '../auth.js';
import { navState } from '../router.js';
import {
  listTrades, createTrade, updateTrade, deleteTrade, searchOpportunities,
  computeGroupKpis, buildMonthlySeries, formatMonthLabel,
} from '../lib/trades.js';

// ── Lazy-load Chart.js (chargé une fois, à la demande) ───────────────────────
const CHARTJS_CDN = 'https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js';
let chartJsPromise = null;
function loadChartJs() {
  if (window.Chart) return Promise.resolve(window.Chart);
  if (chartJsPromise) return chartJsPromise;
  chartJsPromise = new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = CHARTJS_CDN; s.async = true;
    s.onload = () => resolve(window.Chart);
    s.onerror = () => { chartJsPromise = null; reject(new Error('CDN Chart.js injoignable')); };
    document.head.appendChild(s);
  });
  return chartJsPromise;
}

// ── Helpers ──────────────────────────────────────────────────────────────────
const eur = new Intl.NumberFormat('fr-FR', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 });
const eur2 = new Intl.NumberFormat('fr-FR', { style: 'currency', currency: 'EUR', minimumFractionDigits: 0, maximumFractionDigits: 2 });
function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
const CAT_DOT = { urgent: '🔴', interesting: '🟡', passable: '⚫' };
function avatar(t) {
  const name = t.author?.username || '?';
  const color = t.author?.avatar_color || 'var(--accent)';
  return `<span class="jr-avatar" style="background:${esc(color)}">${esc(name[0].toUpperCase())}</span>`;
}

export async function render() {
  const myToken = navState.token;
  await requireAuth();
  if (navState.token !== myToken) return;
  const me = await getProfile();
  if (navState.token !== myToken) return;
  const isAdmin = me?.role === 'admin';

  const root = document.getElementById('appRoot');
  root.innerHTML = `
    <section class="journal-page journal-enter">
      <div class="dash-hero liquid">
        <div class="dash-hero-main">
          <p class="feed-eyebrow">Journal · revente groupe</p>
          <h2 class="dash-title">Profit net du groupe</h2>
          <div class="dash-hero-figure" id="jrHeroProfit">—</div>
          <div class="dash-hero-sub" id="jrHeroSub">Suivez vos deals de A à Z, ensemble.</div>
        </div>
        <button type="button" class="btn btn-primary dash-add-btn" id="jrAddBtn">
          <span aria-hidden="true">＋</span> Ajouter un deal
        </button>
      </div>

      <div class="dash-kpis" id="jrKpis"></div>

      <div class="dash-charts" id="jrCharts">
        <div class="card dash-chart-card">
          <div class="dash-chart-head"><h3>Achats vs ventes <span class="dash-chart-sub">cumul mensuel</span></h3></div>
          <div class="dash-chart-canvas-wrap"><canvas id="jrLineChart" role="img" aria-label="Cumul achats/ventes"></canvas></div>
        </div>
        <div class="card dash-chart-card">
          <div class="dash-chart-head"><h3>Profit net <span class="dash-chart-sub">par mois</span></h3></div>
          <div class="dash-chart-canvas-wrap"><canvas id="jrBarChart" role="img" aria-label="Profit net mensuel"></canvas></div>
        </div>
      </div>

      <div class="jr-board" id="jrBoard">
        <div class="jr-col" data-status="contacted"><div class="jr-col-head">🤝 Contactés <span class="jr-col-count" id="jrCount-contacted"></span></div><div class="jr-col-body" id="jrColBody-contacted"></div></div>
        <div class="jr-col" data-status="bought"><div class="jr-col-head">🛒 Achetés <span class="jr-col-count" id="jrCount-bought"></span></div><div class="jr-col-body" id="jrColBody-bought"></div></div>
        <div class="jr-col" data-status="sold"><div class="jr-col-head">✅ Revendus <span class="jr-col-count" id="jrCount-sold"></span></div><div class="jr-col-body" id="jrColBody-sold"></div></div>
      </div>

      <div class="dash-empty empty-state card hidden" id="jrEmpty">
        <div class="empty-icon" aria-hidden="true">📓</div>
        <h3>Le journal est vide</h3>
        <p>Ajoute ton premier deal — ou lance-toi depuis une annonce du feed avec « Ajouter au journal ».</p>
        <button type="button" class="btn btn-primary" id="jrEmptyAddBtn" style="width:auto"><span aria-hidden="true">＋</span> Ajouter un deal</button>
      </div>
    </section>

    <div class="modal-overlay hidden" id="jrModal">
      <div class="modal-card card" role="dialog" aria-modal="true" aria-labelledby="jrModalTitle">
        <div class="modal-header">
          <div class="modal-title-area"><span class="modal-icon" aria-hidden="true">📓</span><h2 id="jrModalTitle">Nouveau deal</h2></div>
          <button type="button" class="modal-close" id="jrModalClose" aria-label="Fermer">✕</button>
        </div>
        <form class="modal-body dash-form" id="jrForm">
          <input type="hidden" id="jrId">
          <input type="hidden" id="jrOppId">

          <div class="form-group">
            <label for="jrTitle">Article</label>
            <input type="text" id="jrTitle" maxlength="200" required placeholder="Ex : Vélo VTT Decathlon Rockrider">
          </div>

          <div class="form-group">
            <label>Lier une annonce du feed <span class="muted">(optionnel)</span></label>
            <div class="jr-link" id="jrLinkArea">
              <input type="text" id="jrLinkSearch" placeholder="🔎 Rechercher une opportunité…" autocomplete="off">
              <div class="jr-link-results" id="jrLinkResults"></div>
              <div class="jr-link-chosen hidden" id="jrLinkChosen"></div>
            </div>
          </div>

          <div class="form-group">
            <label>Statut</label>
            <div class="dash-type-toggle" id="jrStatus" role="radiogroup" aria-label="Statut">
              <button type="button" class="dash-type-btn is-active" data-status="contacted" role="radio" aria-checked="true">🤝 Contacté</button>
              <button type="button" class="dash-type-btn" data-status="bought" role="radio" aria-checked="false">🛒 Acheté</button>
              <button type="button" class="dash-type-btn" data-status="sold" role="radio" aria-checked="false">✅ Revendu</button>
            </div>
          </div>

          <div class="form-row dash-form-row jr-buy hidden" id="jrBuyRow">
            <div class="form-group"><label for="jrBuyPrice">Prix d'achat (€)</label><input type="number" id="jrBuyPrice" min="0" step="0.01" placeholder="0"></div>
            <div class="form-group"><label for="jrBoughtAt">Date d'achat</label><input type="date" id="jrBoughtAt"></div>
          </div>

          <div class="form-row dash-form-row jr-sell hidden" id="jrSellRow">
            <div class="form-group"><label for="jrSellPrice">Prix de vente (€)</label><input type="number" id="jrSellPrice" min="0" step="0.01" placeholder="0"></div>
            <div class="form-group"><label for="jrSoldAt">Date de vente</label><input type="date" id="jrSoldAt"></div>
          </div>

          <div class="jr-margin hidden" id="jrMargin"></div>

          <div class="form-group">
            <label for="jrNotes">Notes <span class="muted">(optionnel)</span></label>
            <textarea id="jrNotes" rows="2" maxlength="1000" placeholder="Détails, état, négociation…"></textarea>
          </div>

          <div class="dash-form-error form-error hidden" id="jrFormError"></div>
          <div class="actions-area"><button type="submit" class="btn btn-primary" id="jrSubmit">Enregistrer</button></div>
        </form>
      </div>
    </div>`;

  const state = { trades: [], lineChart: null, barChart: null };

  let trades;
  try { trades = await listTrades(); }
  catch (err) {
    if (navState.token !== myToken) return;
    document.getElementById('jrBoard').innerHTML = `<div class="error-panel">❌ ${esc(err.message)}</div>`;
    return;
  }
  if (navState.token !== myToken) return;
  state.trades = trades;

  renderAll();
  wireModal();

  setTimeout(() => root.querySelector('.journal-page')?.classList.remove('journal-enter'), 700);

  try {
    const pre = JSON.parse(sessionStorage.getItem('journal-prefill') || 'null');
    if (pre && pre.opportunity_id) {
      sessionStorage.removeItem('journal-prefill');
      openModal(null, { opportunity_id: pre.opportunity_id, title: pre.title });
    }
  } catch (_) {}

  function renderAll() {
    const has = state.trades.length > 0;
    document.getElementById('jrEmpty').classList.toggle('hidden', has);
    document.getElementById('jrCharts').classList.toggle('hidden', !has);
    document.getElementById('jrBoard').classList.toggle('hidden', !has);
    renderKpis();
    if (has) { renderBoard(); renderCharts(); }
  }

  function renderKpis() {
    const k = computeGroupKpis(state.trades);
    const sign = k.profit > 0 ? '+' : '';
    const pClass = k.profit > 0 ? 'is-positive' : k.profit < 0 ? 'is-negative' : '';
    const roiTxt = k.roi == null ? 'n/d' : `${k.roi > 0 ? '+' : ''}${k.roi.toFixed(1).replace('.', ',')} %`;

    document.getElementById('jrHeroProfit').textContent = `${sign}${eur.format(k.profit)}`;
    document.getElementById('jrHeroProfit').className = `dash-hero-figure ${pClass}`;
    document.getElementById('jrHeroSub').textContent =
      `ROI ${roiTxt} · ${k.counts.sold} revendu${k.counts.sold > 1 ? 's' : ''} / ${k.counts.bought} acheté${k.counts.bought > 1 ? 's' : ''} / ${k.counts.contacted} contacté${k.counts.contacted > 1 ? 's' : ''}`;

    document.getElementById('jrKpis').innerHTML = `
      ${kpi('💰', 'accent-blue', 'Total investi', eur.format(k.invested), 'achats des deals revendus')}
      ${kpi('💵', 'accent-green', 'Total encaissé', eur.format(k.earned), 'ventes réalisées')}
      ${kpi('📈', 'accent-purple', 'Profit net', `${sign}${eur.format(k.profit)}`, 'marge réalisée', pClass)}
      ${kpi('🎯', 'accent-amber', 'ROI', roiTxt, 'retour sur investissement')}`;
  }

  function cardHtml(t) {
    const canEdit = t.user_id === me?.id || isAdmin;
    const margin = (t.status === 'sold' && t.buy_price != null && t.sell_price != null)
      ? Number(t.sell_price) - Number(t.buy_price) : null;
    const priceLine =
      t.status === 'sold'
        ? `<span class="jr-card-price">Achat ${t.buy_price != null ? eur2.format(t.buy_price) : '—'} → Vente ${t.sell_price != null ? eur2.format(t.sell_price) : '—'}</span>`
        : t.status === 'bought'
          ? `<span class="jr-card-price">Payé ${t.buy_price != null ? eur2.format(t.buy_price) : '—'}</span>`
          : '';
    const marginBadge = margin != null
      ? `<span class="jr-card-margin ${margin >= 0 ? 'is-positive' : 'is-negative'}">${margin >= 0 ? '+' : ''}${eur2.format(margin)}</span>` : '';
    const actions = canEdit
      ? `<div class="jr-card-actions">
           <button type="button" class="jr-icon-btn" data-action="edit" data-id="${t.id}" title="Modifier" aria-label="Modifier">✏️</button>
           <button type="button" class="jr-icon-btn jr-icon-danger" data-action="delete" data-id="${t.id}" title="Supprimer" aria-label="Supprimer">🗑️</button>
         </div>` : '';
    return `
      <div class="jr-card" data-id="${t.id}">
        <div class="jr-card-top">
          <span class="jr-card-title">${esc(t.title)}</span>
          ${marginBadge}
        </div>
        <div class="jr-card-meta">${avatar(t)} <span class="jr-card-author">${esc(t.author?.username || 'Anonyme')}</span></div>
        ${priceLine ? `<div class="jr-card-prices">${priceLine}</div>` : ''}
        ${actions}
      </div>`;
  }

  function renderBoard() {
    for (const st of ['contacted', 'bought', 'sold']) {
      const list = state.trades.filter(t => t.status === st);
      const body = document.getElementById('jrColBody-' + st);
      const count = document.getElementById('jrCount-' + st);
      count.textContent = list.length ? `(${list.length})` : '';
      body.innerHTML = list.length
        ? list.map(cardHtml).join('')
        : `<div class="jr-col-empty muted">Aucun deal.</div>`;
    }
    document.getElementById('jrBoard').onclick = onBoardClick;
  }

  async function onBoardClick(e) {
    const btn = e.target.closest('button[data-action]');
    const card = e.target.closest('.jr-card');
    if (btn) {
      const t = state.trades.find(x => x.id === btn.dataset.id);
      if (!t) return;
      if (btn.dataset.action === 'edit') { openModal(t); return; }
      if (btn.dataset.action === 'delete') {
        if (!confirm(`Supprimer « ${t.title} » ?`)) return;
        try { await deleteTrade(t.id); state.trades = state.trades.filter(x => x.id !== t.id); renderAll(); }
        catch (err) { alert(err.message); }
      }
      return;
    }
    if (card) {
      const t = state.trades.find(x => x.id === card.dataset.id);
      if (t) openModal(t);
    }
  }

  async function renderCharts() {
    const { labels, buysCumul, sellsCumul, profitMonthly } = buildMonthlySeries(state.trades);
    const lineCanvas = document.getElementById('jrLineChart');
    const barCanvas = document.getElementById('jrBarChart');
    if (!lineCanvas || !barCanvas) return;
    if (!labels.length) { document.getElementById('jrCharts').classList.add('hidden'); return; }

    let Chart;
    try { Chart = await loadChartJs(); }
    catch (_) {
      document.getElementById('jrCharts').innerHTML =
        `<div class="card dash-chart-fallback">📉 Graphiques indisponibles (Chart.js injoignable). Les KPIs et le tableau restent à jour.</div>`;
      return;
    }
    if (navState.token !== myToken) return;
    state.lineChart?.destroy(); state.barChart?.destroy();

    const css = getComputedStyle(document.documentElement);
    const COL = (n, f) => (css.getPropertyValue(n).trim() || f);
    const blue = COL('--accent-blue', '#f5963c'), green = COL('--accent-green', '#34d399'),
      rose = COL('--accent-rose', '#fb5b76'), textSec = COL('--text-secondary', '#78716c'),
      grid = COL('--chart-grid', 'rgba(0,0,0,0.06)');
    const monthLabels = labels.map(formatMonthLabel);
    Chart.defaults.font.family = "'Outfit', system-ui, sans-serif";
    Chart.defaults.color = textSec;
    const scales = { x: { grid: { color: grid }, ticks: { color: textSec } },
      y: { grid: { color: grid }, ticks: { color: textSec, callback: v => eur.format(v) }, beginAtZero: true } };
    const tooltip = { callbacks: { label: ctx => `${ctx.dataset.label} : ${eur2.format(ctx.parsed.y)}` } };

    state.lineChart = new Chart(lineCanvas, {
      type: 'line',
      data: { labels: monthLabels, datasets: [
        { label: 'Achats (cumul)', data: buysCumul, borderColor: blue, backgroundColor: hexA(blue, .12), fill: true, tension: .3 },
        { label: 'Ventes (cumul)', data: sellsCumul, borderColor: green, backgroundColor: hexA(green, .12), fill: true, tension: .3 },
      ] },
      options: { responsive: true, maintainAspectRatio: false, interaction: { mode: 'index', intersect: false },
        plugins: { legend: { labels: { color: textSec, usePointStyle: true, boxWidth: 8 } }, tooltip }, scales },
    });
    state.barChart = new Chart(barCanvas, {
      type: 'bar',
      data: { labels: monthLabels, datasets: [{ label: 'Profit net', data: profitMonthly,
        backgroundColor: profitMonthly.map(v => v >= 0 ? hexA(green, .6) : hexA(rose, .6)),
        borderColor: profitMonthly.map(v => v >= 0 ? green : rose), borderWidth: 1, borderRadius: 6 }] },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip }, scales },
    });
  }

  function wireModal() {
    document.getElementById('jrAddBtn').addEventListener('click', () => openModal(null));
    document.getElementById('jrEmptyAddBtn').addEventListener('click', () => openModal(null));
    document.getElementById('jrModalClose').addEventListener('click', closeModal);
    document.getElementById('jrModal').addEventListener('click', e => { if (e.target.id === 'jrModal') closeModal(); });
    document.addEventListener('keydown', onEsc);

    document.getElementById('jrStatus').addEventListener('click', e => {
      const b = e.target.closest('.dash-type-btn'); if (!b) return;
      document.querySelectorAll('#jrStatus .dash-type-btn').forEach(x => {
        const on = x === b; x.classList.toggle('is-active', on); x.setAttribute('aria-checked', on ? 'true' : 'false');
      });
      syncStatusFields();
    });
    document.getElementById('jrBuyPrice').addEventListener('input', syncMargin);
    document.getElementById('jrSellPrice').addEventListener('input', syncMargin);

    wireLinkSearch();
    document.getElementById('jrForm').addEventListener('submit', onSubmit);
  }

  function onEsc(e) { if (e.key === 'Escape') closeModal(); }
  function currentStatus() { return document.querySelector('#jrStatus .dash-type-btn.is-active')?.dataset.status || 'contacted'; }

  function syncStatusFields() {
    const st = currentStatus();
    document.getElementById('jrBuyRow').classList.toggle('hidden', st === 'contacted');
    document.getElementById('jrSellRow').classList.toggle('hidden', st !== 'sold');
    syncMargin();
  }
  function syncMargin() {
    const st = currentStatus();
    const b = parseFloat(document.getElementById('jrBuyPrice').value);
    const s = parseFloat(document.getElementById('jrSellPrice').value);
    const box = document.getElementById('jrMargin');
    if (st === 'sold' && b >= 0 && s >= 0 && !isNaN(b) && !isNaN(s)) {
      const m = s - b;
      box.className = `jr-margin ${m >= 0 ? 'is-positive' : 'is-negative'}`;
      box.textContent = `Marge : ${m >= 0 ? '+' : ''}${eur2.format(m)}`;
      box.classList.remove('hidden');
    } else { box.classList.add('hidden'); }
  }

  function setStatusUI(status) {
    document.querySelectorAll('#jrStatus .dash-type-btn').forEach(x => {
      const on = x.dataset.status === status;
      x.classList.toggle('is-active', on); x.setAttribute('aria-checked', on ? 'true' : 'false');
    });
    syncStatusFields();
  }
  function setLinkedOpp(opp) {
    const chosen = document.getElementById('jrLinkChosen');
    const search = document.getElementById('jrLinkSearch');
    document.getElementById('jrLinkResults').innerHTML = '';
    if (opp && opp.opportunity_id) {
      document.getElementById('jrOppId').value = opp.opportunity_id;
      chosen.innerHTML = `🔗 ${esc(opp.title || 'Annonce liée')} <button type="button" class="jr-link-clear" id="jrLinkClear">✕ délier</button>`;
      chosen.classList.remove('hidden'); search.classList.add('hidden');
      document.getElementById('jrLinkClear').addEventListener('click', () => setLinkedOpp(null));
    } else {
      document.getElementById('jrOppId').value = '';
      chosen.classList.add('hidden'); chosen.innerHTML = '';
      search.classList.remove('hidden'); search.value = '';
    }
  }

  function wireLinkSearch() {
    const search = document.getElementById('jrLinkSearch');
    const results = document.getElementById('jrLinkResults');
    let timer = null;
    search.addEventListener('input', () => {
      clearTimeout(timer);
      const q = search.value.trim();
      if (q.length < 2) { results.innerHTML = ''; return; }
      timer = setTimeout(async () => {
        const opps = await searchOpportunities(q);
        results.innerHTML = opps.length
          ? opps.map(o => `<button type="button" class="jr-link-item" data-id="${o.id}" data-title="${esc(o.title)}">
               ${CAT_DOT[o.category] || '⚫'} ${esc(o.title)} <span class="muted">${o.price != null ? eur.format(o.price) : ''}</span></button>`).join('')
          : `<div class="jr-link-empty muted">Aucune annonce trouvée.</div>`;
      }, 250);
    });
    results.addEventListener('click', e => {
      const it = e.target.closest('.jr-link-item'); if (!it) return;
      setLinkedOpp({ opportunity_id: it.dataset.id, title: it.dataset.title });
      const titleEl = document.getElementById('jrTitle');
      if (!titleEl.value.trim()) titleEl.value = it.dataset.title;
    });
  }

  function openModal(trade, prefill) {
    document.getElementById('jrFormError').classList.add('hidden');
    document.getElementById('jrId').value = trade?.id || '';
    document.getElementById('jrModalTitle').textContent = trade ? 'Modifier le deal' : 'Nouveau deal';
    document.getElementById('jrTitle').value = trade?.title || prefill?.title || '';
    document.getElementById('jrBuyPrice').value = trade?.buy_price ?? '';
    document.getElementById('jrSellPrice').value = trade?.sell_price ?? '';
    document.getElementById('jrBoughtAt').value = trade?.bought_at || '';
    document.getElementById('jrSoldAt').value = trade?.sold_at || '';
    document.getElementById('jrNotes').value = trade?.notes || '';
    setStatusUI(trade?.status || 'contacted');
    if (trade?.opportunity_id) setLinkedOpp({ opportunity_id: trade.opportunity_id, title: trade.title });
    else if (prefill?.opportunity_id) setLinkedOpp({ opportunity_id: prefill.opportunity_id, title: prefill.title });
    else setLinkedOpp(null);
    document.getElementById('jrModal').classList.remove('hidden');
    setTimeout(() => document.getElementById('jrTitle')?.focus(), 50);
  }
  function closeModal() { document.getElementById('jrModal').classList.add('hidden'); }

  async function onSubmit(e) {
    e.preventDefault();
    const err = document.getElementById('jrFormError');
    const submit = document.getElementById('jrSubmit');
    err.classList.add('hidden');

    const id = document.getElementById('jrId').value;
    const status = currentStatus();
    const title = document.getElementById('jrTitle').value.trim();
    const buy = document.getElementById('jrBuyPrice').value;
    const sell = document.getElementById('jrSellPrice').value;

    if (!title) return showErr('Indique le nom de l\'article.');
    if ((status === 'bought' || status === 'sold') && !(parseFloat(buy) >= 0)) return showErr('Indique le prix d\'achat.');
    if (status === 'sold' && !(parseFloat(sell) >= 0)) return showErr('Indique le prix de vente.');

    const todayISO = new Date().toISOString().slice(0, 10);
    const payload = {
      title, status,
      opportunity_id: document.getElementById('jrOppId').value || null,
      buy_price: buy, sell_price: sell,
      bought_at: document.getElementById('jrBoughtAt').value || (status !== 'contacted' ? todayISO : null),
      sold_at: document.getElementById('jrSoldAt').value || (status === 'sold' ? todayISO : null),
      notes: document.getElementById('jrNotes').value,
    };

    submit.disabled = true; submit.textContent = 'Enregistrement…';
    try {
      if (id) {
        const up = await updateTrade(id, payload);
        const i = state.trades.findIndex(t => t.id === id);
        if (i >= 0) state.trades[i] = up;
      } else {
        const created = await createTrade(payload);
        state.trades.unshift(created);
      }
      state.trades.sort((a, b) => (b.updated_at || '').localeCompare(a.updated_at || ''));
      closeModal(); renderAll();
    } catch (e2) { showErr(e2.message); }
    finally { submit.disabled = false; submit.textContent = 'Enregistrer'; }
  }
  function showErr(msg) { const e = document.getElementById('jrFormError'); e.textContent = msg; e.classList.remove('hidden'); }
}

// ── Helpers hors closure ─────────────────────────────────────────────────────
function kpi(emoji, accent, label, value, sub, valueClass = '') {
  return `<div class="card dash-kpi dash-kpi--${accent}">
      <div class="dash-kpi-icon" aria-hidden="true">${emoji}</div>
      <div class="dash-kpi-body">
        <span class="dash-kpi-label">${label}</span>
        <span class="dash-kpi-value ${valueClass}">${value}</span>
        <span class="dash-kpi-sub">${sub}</span>
      </div></div>`;
}
function hexA(hex, alpha) {
  const h = String(hex).replace('#', '').trim();
  if (h.length !== 6) return hex;
  return `rgba(${parseInt(h.slice(0,2),16)}, ${parseInt(h.slice(2,4),16)}, ${parseInt(h.slice(4,6),16)}, ${alpha})`;
}
