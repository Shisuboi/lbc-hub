// js/pages/dashboard.js
// Page /dashboard : tableau de bord financier privé de l'utilisateur.
// KPIs + 2 graphiques Chart.js (lazy-loadé) + table d'historique + modal CRUD.
// Données strictement privées : la RLS Supabase filtre sur (select auth.uid()).
import { supa } from '../supabase-client.js';
import { requireAuth } from '../auth.js';
import { navState } from '../router.js';
import {
    listTransactions, createTransaction, updateTransaction, deleteTransaction,
    computeKpis, buildMonthlySeries, formatMonthLabel,
} from '../lib/transactions.js';

// ── Lazy-load Chart.js (cf. plan D-DASH-02) : chargé UNE fois, à la demande ─────
const CHARTJS_CDN = 'https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js';
let chartJsPromise = null;
function loadChartJs() {
    if (window.Chart) return Promise.resolve(window.Chart);
    if (chartJsPromise) return chartJsPromise;
    chartJsPromise = new Promise((resolve, reject) => {
        const s = document.createElement('script');
        s.src = CHARTJS_CDN;
        s.async = true;
        s.onload = () => resolve(window.Chart);
        s.onerror = () => { chartJsPromise = null; reject(new Error('CDN Chart.js injoignable')); };
        document.head.appendChild(s);
    });
    return chartJsPromise;
}

// ── Helpers de formatage ────────────────────────────────────────────────────
const eur = new Intl.NumberFormat('fr-FR', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 });
const eur2 = new Intl.NumberFormat('fr-FR', { style: 'currency', currency: 'EUR', minimumFractionDigits: 2, maximumFractionDigits: 2 });
function fmtDate(d) {
    if (!d) return '';
    const [y, m, day] = String(d).split('-');
    return `${day}/${m}/${y}`;
}
function escapeHtml(s) {
    return String(s ?? '').replace(/[&<>"']/g, c => (
        { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
    ));
}

export async function render() {
    const myToken = navState.token;
    await requireAuth();
    if (navState.token !== myToken) return;

    const root = document.getElementById('appRoot');
    root.innerHTML = `
        <section class="dash-page">
            <div class="dash-head">
                <div class="dash-head-titles">
                    <h2 class="dash-title">📊 Tableau de bord financier</h2>
                    <p class="dash-subtitle">Suis tes achats, tes ventes et ta rentabilité sur la revente.</p>
                </div>
                <button type="button" class="btn btn-primary dash-add-btn" id="dashAddBtn">
                    <span aria-hidden="true">＋</span> Ajouter une transaction
                </button>
            </div>

            <div class="dash-kpis" id="dashKpis" aria-busy="true">
                ${kpiSkeleton()}
            </div>

            <div class="dash-charts" id="dashCharts">
                <div class="card dash-chart-card">
                    <div class="dash-chart-head">
                        <h3>Achats vs ventes <span class="dash-chart-sub">cumul mensuel</span></h3>
                    </div>
                    <div class="dash-chart-canvas-wrap">
                        <canvas id="dashLineChart" role="img" aria-label="Courbe cumulée des achats et des ventes par mois"></canvas>
                    </div>
                </div>
                <div class="card dash-chart-card">
                    <div class="dash-chart-head">
                        <h3>Profit net <span class="dash-chart-sub">par mois</span></h3>
                    </div>
                    <div class="dash-chart-canvas-wrap">
                        <canvas id="dashBarChart" role="img" aria-label="Profit net mensuel"></canvas>
                    </div>
                </div>
            </div>

            <div class="card dash-table-card">
                <div class="dash-table-head">
                    <h3>Historique des transactions</h3>
                    <span class="muted small" id="dashTxCount"></span>
                </div>
                <div id="dashTableWrap" class="dash-table-wrap"></div>
            </div>

            <div class="dash-empty empty-state card hidden" id="dashEmpty">
                <div class="empty-icon" aria-hidden="true">📈</div>
                <h3>Aucune transaction pour l'instant</h3>
                <p>Ajoute ton premier achat ou ta première vente pour voir tes KPIs et tes graphiques se construire.</p>
                <button type="button" class="btn btn-primary" id="dashEmptyAddBtn" style="width:auto">
                    <span aria-hidden="true">＋</span> Ajouter ma première transaction
                </button>
            </div>
        </section>

        <div class="modal-overlay hidden" id="dashModal">
            <div class="modal-card card" role="dialog" aria-modal="true" aria-labelledby="dashModalTitle">
                <div class="modal-header">
                    <div class="modal-title-area">
                        <span class="modal-icon" aria-hidden="true">💸</span>
                        <h2 id="dashModalTitle">Nouvelle transaction</h2>
                    </div>
                    <button type="button" class="modal-close" id="dashModalClose" aria-label="Fermer">✕</button>
                </div>
                <form class="modal-body dash-form" id="dashForm">
                    <input type="hidden" id="dashTxId">

                    <div class="form-group">
                        <label>Type d'opération</label>
                        <div class="dash-type-toggle" id="dashType" role="radiogroup" aria-label="Type d'opération">
                            <button type="button" class="dash-type-btn is-active" data-type="achat" role="radio" aria-checked="true">🛒 Achat</button>
                            <button type="button" class="dash-type-btn" data-type="vente" role="radio" aria-checked="false">💰 Vente</button>
                        </div>
                    </div>

                    <div class="form-group">
                        <label for="dashLabel">Article</label>
                        <input type="text" id="dashLabel" maxlength="200" required placeholder="Ex : Vélo VTT Decathlon Rockrider">
                    </div>

                    <div class="form-row dash-form-row">
                        <div class="form-group">
                            <label for="dashAmount">Montant (€)</label>
                            <input type="number" id="dashAmount" min="0.01" step="0.01" required placeholder="0,00">
                        </div>
                        <div class="form-group">
                            <label for="dashDate">Date</label>
                            <input type="date" id="dashDate" required>
                        </div>
                    </div>

                    <div class="form-group">
                        <label for="dashUrl">Lien de l'annonce <span class="muted">(optionnel)</span></label>
                        <input type="url" id="dashUrl" placeholder="https://www.leboncoin.fr/...">
                    </div>

                    <div class="dash-form-error form-error hidden" id="dashFormError"></div>

                    <div class="actions-area">
                        <button type="submit" class="btn btn-primary" id="dashSubmit">Enregistrer</button>
                    </div>
                </form>
            </div>
        </div>
    `;

    // ── State ────────────────────────────────────────────────────────────────
    const state = { transactions: [], lineChart: null, barChart: null };

    // ── Fetch transactions + recherches du user (pour le select de liaison) ────
    let transactions;
    try {
        transactions = await listTransactions();
    } catch (err) {
        if (navState.token !== myToken) return;
        document.getElementById('dashTableWrap').innerHTML =
            `<div class="error-panel">❌ ${escapeHtml(err.message)}</div>`;
        document.getElementById('dashKpis').removeAttribute('aria-busy');
        return;
    }
    if (navState.token !== myToken) return;
    state.transactions = transactions;

    const { data: { session } } = await supa.auth.getSession();
    if (navState.token !== myToken) return;

    // ── Premier rendu ──────────────────────────────────────────────────────────
    renderAll();
    wireModal();

    // ============================================================================
    // Rendu global (KPIs + table + charts + bascule empty state)
    // ============================================================================
    function renderAll() {
        const hasData = state.transactions.length > 0;
        document.getElementById('dashEmpty')?.classList.toggle('hidden', hasData);
        document.getElementById('dashCharts')?.classList.toggle('hidden', !hasData);
        document.getElementById('dashKpis')?.classList.toggle('hidden', !hasData);
        document.querySelector('.dash-table-card')?.classList.toggle('hidden', !hasData);

        if (!hasData) return;

        renderKpis();
        renderTable();
        renderCharts();
    }

    function renderKpis() {
        const k = computeKpis(state.transactions);
        const kpis = document.getElementById('dashKpis');
        if (!kpis) return;
        kpis.removeAttribute('aria-busy');

        const profitClass = k.profit > 0 ? 'is-positive' : k.profit < 0 ? 'is-negative' : '';
        const profitSign = k.profit > 0 ? '+' : '';
        const roiText = k.roi === null ? 'n/d' : `${k.roi > 0 ? '+' : ''}${k.roi.toFixed(1).replace('.', ',')} %`;
        const roiClass = k.roi === null ? '' : k.roi > 0 ? 'is-positive' : k.roi < 0 ? 'is-negative' : '';

        kpis.innerHTML = `
            ${kpiCard('💰', 'accent-blue', 'Total investi', eur.format(k.invested), `${k.buyCount} achat${k.buyCount > 1 ? 's' : ''}`)}
            ${kpiCard('💵', 'accent-green', 'Total encaissé', eur.format(k.earned), `${k.sellCount} vente${k.sellCount > 1 ? 's' : ''}`)}
            ${kpiCard('📈', 'accent-purple', 'Profit net', `${profitSign}${eur.format(k.profit)}`, 'ventes − achats', profitClass)}
            ${kpiCard('🎯', 'accent-amber', 'ROI', roiText, 'retour sur investissement', roiClass)}
        `;
    }

    function renderTable() {
        const wrap = document.getElementById('dashTableWrap');
        const count = document.getElementById('dashTxCount');
        if (!wrap) return;
        if (count) count.textContent = `${state.transactions.length} transaction${state.transactions.length > 1 ? 's' : ''}`;

        const rows = state.transactions.map(t => {
            const isSale = t.type === 'vente';
            const amountClass = isSale ? 'is-positive' : 'is-negative';
            const amountStr = `${isSale ? '+' : '−'}${eur2.format(t.amount)}`;
            const link = t.url
                ? `<a href="${escapeHtml(t.url)}" target="_blank" rel="noopener noreferrer" class="dash-row-link" title="Ouvrir l'annonce">↗</a>`
                : '';
            return `
                <tr data-tx-id="${t.id}">
                    <td class="dash-col-date">${fmtDate(t.date)}</td>
                    <td class="dash-col-type">
                        <span class="dash-badge ${isSale ? 'dash-badge-sale' : 'dash-badge-buy'}">
                            ${isSale ? '💰 Vente' : '🛒 Achat'}
                        </span>
                    </td>
                    <td class="dash-col-label">${escapeHtml(t.label)} ${link}</td>
                    <td class="dash-col-amount ${amountClass}">${amountStr}</td>
                    <td class="dash-col-actions">
                        <button type="button" class="dash-icon-btn" data-action="edit" data-id="${t.id}" title="Modifier" aria-label="Modifier">✏️</button>
                        <button type="button" class="dash-icon-btn dash-icon-danger" data-action="delete" data-id="${t.id}" title="Supprimer" aria-label="Supprimer">🗑️</button>
                    </td>
                </tr>`;
        }).join('');

        wrap.innerHTML = `
            <table class="dash-table">
                <thead>
                    <tr>
                        <th class="dash-col-date">Date</th>
                        <th class="dash-col-type">Type</th>
                        <th class="dash-col-label">Article</th>
                        <th class="dash-col-amount">Montant</th>
                        <th class="dash-col-actions" aria-label="Actions"></th>
                    </tr>
                </thead>
                <tbody>${rows}</tbody>
            </table>`;

        // Délégation des actions edit / delete
        const tbody = wrap.querySelector('tbody');
        tbody?.addEventListener('click', onTableAction);
    }

    async function onTableAction(e) {
        const btn = e.target.closest('button[data-action]');
        if (!btn) return;
        const id = btn.dataset.id;
        const tx = state.transactions.find(t => t.id === id);
        if (!tx) return;

        if (btn.dataset.action === 'edit') {
            openModal(tx);
            return;
        }
        if (btn.dataset.action === 'delete') {
            if (!confirm(`Supprimer « ${tx.label} » (${eur2.format(tx.amount)}) ?`)) return;
            btn.disabled = true;
            try {
                await deleteTransaction(id);
                state.transactions = state.transactions.filter(t => t.id !== id);
                renderAll();
            } catch (err) {
                alert(err.message);
                btn.disabled = false;
            }
        }
    }

    async function renderCharts() {
        const { labels, buysCumul, sellsCumul, profitMonthly } = buildMonthlySeries(state.transactions);
        const lineCanvas = document.getElementById('dashLineChart');
        const barCanvas = document.getElementById('dashBarChart');
        if (!lineCanvas || !barCanvas) return;

        let Chart;
        try {
            Chart = await loadChartJs();
        } catch (_) {
            // Fallback gracieux si le CDN est injoignable : on garde KPIs + table.
            const charts = document.getElementById('dashCharts');
            if (charts) charts.innerHTML =
                `<div class="card dash-chart-fallback">📉 Graphiques indisponibles (Chart.js n'a pas pu être chargé). Les KPIs et l'historique ci-dessous restent à jour.</div>`;
            return;
        }
        if (navState.token !== myToken) return;

        // Détruit les instances précédentes avant re-render (évite les fuites canvas).
        state.lineChart?.destroy();
        state.barChart?.destroy();

        const css = getComputedStyle(document.documentElement);
        const COL = (name, fallback) => (css.getPropertyValue(name).trim() || fallback);
        const blue = COL('--accent-blue', '#38bdf8');
        const green = COL('--accent-green', '#10b981');
        const rose = COL('--accent-rose', '#f43f5e');
        const textSec = COL('--text-secondary', '#94a3b8');
        const grid = 'rgba(255,255,255,0.06)';
        const monthLabels = labels.map(formatMonthLabel);

        Chart.defaults.font.family = "'Outfit', system-ui, sans-serif";
        Chart.defaults.color = textSec;

        const baseScales = {
            x: { grid: { color: grid }, ticks: { color: textSec } },
            y: {
                grid: { color: grid }, ticks: { color: textSec, callback: v => eur.format(v) },
                beginAtZero: true,
            },
        };
        const tooltip = {
            backgroundColor: 'rgba(6,9,19,0.92)', borderColor: 'rgba(255,255,255,0.1)', borderWidth: 1,
            titleColor: '#f8fafc', bodyColor: '#cbd5e1', padding: 10, cornerRadius: 8,
            callbacks: { label: ctx => `${ctx.dataset.label} : ${eur2.format(ctx.parsed.y)}` },
        };

        state.lineChart = new Chart(lineCanvas, {
            type: 'line',
            data: {
                labels: monthLabels,
                datasets: [
                    { label: 'Achats (cumul)', data: buysCumul, borderColor: blue, backgroundColor: hexA(blue, 0.12), fill: true, tension: 0.3, pointRadius: 3, pointBackgroundColor: blue },
                    { label: 'Ventes (cumul)', data: sellsCumul, borderColor: green, backgroundColor: hexA(green, 0.12), fill: true, tension: 0.3, pointRadius: 3, pointBackgroundColor: green },
                ],
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: { legend: { labels: { color: textSec, usePointStyle: true, boxWidth: 8 } }, tooltip },
                scales: baseScales,
            },
        });

        state.barChart = new Chart(barCanvas, {
            type: 'bar',
            data: {
                labels: monthLabels,
                datasets: [{
                    label: 'Profit net',
                    data: profitMonthly,
                    backgroundColor: profitMonthly.map(v => v >= 0 ? hexA(green, 0.6) : hexA(rose, 0.6)),
                    borderColor: profitMonthly.map(v => v >= 0 ? green : rose),
                    borderWidth: 1, borderRadius: 6,
                }],
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                plugins: { legend: { display: false }, tooltip },
                scales: baseScales,
            },
        });
    }

    // ============================================================================
    // Modal CRUD
    // ============================================================================
    function wireModal() {
        const modal = document.getElementById('dashModal');
        const form = document.getElementById('dashForm');
        document.getElementById('dashAddBtn')?.addEventListener('click', () => openModal(null));
        document.getElementById('dashEmptyAddBtn')?.addEventListener('click', () => openModal(null));
        document.getElementById('dashModalClose')?.addEventListener('click', closeModal);
        modal?.addEventListener('click', (e) => { if (e.target === modal) closeModal(); });
        document.addEventListener('keydown', onEsc);

        // Toggle type achat/vente
        document.getElementById('dashType')?.addEventListener('click', (e) => {
            const b = e.target.closest('.dash-type-btn');
            if (!b) return;
            document.querySelectorAll('#dashType .dash-type-btn').forEach(x => {
                const active = x === b;
                x.classList.toggle('is-active', active);
                x.setAttribute('aria-checked', active ? 'true' : 'false');
            });
        });

        form?.addEventListener('submit', onSubmit);
    }

    function onEsc(e) {
        if (e.key === 'Escape') closeModal();
    }

    function openModal(tx) {
        const modal = document.getElementById('dashModal');
        const err = document.getElementById('dashFormError');
        err?.classList.add('hidden');
        document.getElementById('dashTxId').value = tx?.id || '';
        document.getElementById('dashModalTitle').textContent = tx ? 'Modifier la transaction' : 'Nouvelle transaction';
        document.getElementById('dashLabel').value = tx?.label || '';
        document.getElementById('dashAmount').value = tx?.amount ?? '';
        document.getElementById('dashDate').value = tx?.date || new Date().toISOString().slice(0, 10);
        document.getElementById('dashUrl').value = tx?.url || '';
        const type = tx?.type || 'achat';
        document.querySelectorAll('#dashType .dash-type-btn').forEach(x => {
            const active = x.dataset.type === type;
            x.classList.toggle('is-active', active);
            x.setAttribute('aria-checked', active ? 'true' : 'false');
        });
        modal?.classList.remove('hidden');
        setTimeout(() => document.getElementById('dashLabel')?.focus(), 50);
    }

    function closeModal() {
        document.getElementById('dashModal')?.classList.add('hidden');
    }

    async function onSubmit(e) {
        e.preventDefault();
        const err = document.getElementById('dashFormError');
        const submitBtn = document.getElementById('dashSubmit');
        err.classList.add('hidden');

        const id = document.getElementById('dashTxId').value;
        const type = document.querySelector('#dashType .dash-type-btn.is-active')?.dataset.type || 'achat';
        const label = document.getElementById('dashLabel').value.trim();
        const amount = parseFloat(document.getElementById('dashAmount').value);
        const date = document.getElementById('dashDate').value;
        const url = document.getElementById('dashUrl').value.trim() || null;

        if (!label) return showFormError('Indique le nom de l\'article.');
        if (!(amount > 0)) return showFormError('Le montant doit être supérieur à 0.');
        if (!date) return showFormError('Choisis une date.');

        submitBtn.disabled = true;
        submitBtn.textContent = 'Enregistrement…';
        const payload = { type, label, amount, date, search_id: null, url };
        try {
            if (id) {
                const updated = await updateTransaction(id, payload);
                const i = state.transactions.findIndex(t => t.id === id);
                if (i >= 0) state.transactions[i] = updated;
            } else {
                const created = await createTransaction(payload);
                state.transactions.unshift(created);
            }
            // Re-tri par date décroissante (la création peut être antidatée)
            state.transactions.sort((a, b) =>
                (b.date || '').localeCompare(a.date || '') ||
                (b.created_at || '').localeCompare(a.created_at || ''));
            closeModal();
            renderAll();
        } catch (err2) {
            showFormError(err2.message);
        } finally {
            submitBtn.disabled = false;
            submitBtn.textContent = 'Enregistrer';
        }
    }

    function showFormError(msg) {
        const err = document.getElementById('dashFormError');
        if (err) { err.textContent = msg; err.classList.remove('hidden'); }
    }
}

// ── Petits helpers de rendu (hors closure : pas d'état) ─────────────────────
function kpiCard(emoji, accent, label, value, sub, valueClass = '') {
    return `
        <div class="card dash-kpi dash-kpi--${accent}">
            <div class="dash-kpi-icon" aria-hidden="true">${emoji}</div>
            <div class="dash-kpi-body">
                <span class="dash-kpi-label">${label}</span>
                <span class="dash-kpi-value ${valueClass}">${value}</span>
                <span class="dash-kpi-sub">${sub}</span>
            </div>
        </div>`;
}

function kpiSkeleton() {
    return Array.from({ length: 4 }).map(() => `
        <div class="card dash-kpi dash-kpi--skeleton">
            <div class="dash-kpi-icon dash-sk"></div>
            <div class="dash-kpi-body">
                <span class="dash-sk dash-sk-line" style="width:60%"></span>
                <span class="dash-sk dash-sk-line" style="width:80%;height:1.6rem"></span>
                <span class="dash-sk dash-sk-line" style="width:40%"></span>
            </div>
        </div>`).join('');
}

// Convertit une couleur hex (#rrggbb) en rgba avec alpha. Fallback si déjà rgb.
function hexA(hex, alpha) {
    const h = hex.replace('#', '').trim();
    if (h.length !== 6) return hex;
    const r = parseInt(h.slice(0, 2), 16);
    const g = parseInt(h.slice(2, 4), 16);
    const b = parseInt(h.slice(4, 6), 16);
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}
