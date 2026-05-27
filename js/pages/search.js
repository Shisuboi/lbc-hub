// js/pages/search.js
// Page /search/:id — détail d'une recherche publiée :
//   - bandeau modèle (cloud/local)
//   - méta : auteur, plateforme, date de scraping, URL source
//   - filtres : texte, score min, tri (note/prix)
//   - grille de listing cards
import { supa } from '../supabase-client.js';
import { requireAuth } from '../auth.js';
import { listingCardHtml } from '../components/listing-card.js';
import { avatarHtml } from '../lib/colors.js';

function escapeHtml(s) {
    if (s == null) return '';
    return String(s).replace(/[&<>"']/g, c => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[c]));
}

const PLATFORM_LABEL = {
    leboncoin: '🟠 Leboncoin',
    ebay:      '🔵 eBay',
    vinted:    '🟢 Vinted',
    other:     '⚪ Autre',
};

export async function render({ id }) {
    await requireAuth();

    const root = document.getElementById('appRoot');
    root.innerHTML = '<div class="page-loading">⏳ Chargement de la recherche…</div>';

    // Fetch search + listings en parallèle
    const [searchResp, listingsResp] = await Promise.all([
        supa.from('searches').select('*').eq('id', id).single(),
        supa.from('listings')
            .select('*')
            .eq('search_id', id)
            .order('note_sur_100', { ascending: false }),
    ]);

    if (searchResp.error || !searchResp.data) {
        root.innerHTML = `
            <div class="error-panel card">
                <h2>Recherche introuvable</h2>
                <p>${searchResp.error?.message || 'La recherche demandée n\'existe pas ou a été supprimée.'}</p>
                <a href="/hub" data-link class="btn btn-primary">Retour au hub</a>
            </div>`;
        return;
    }

    const search = searchResp.data;
    const listings = listingsResp.data || [];

    const { data: author } = await supa
        .from('profiles')
        .select('id, username, avatar_color')
        .eq('id', search.user_id)
        .single();

    const isCloud = search.model_type === 'cloud';
    const platform = PLATFORM_LABEL[search.platform] || PLATFORM_LABEL.other;
    const scrapedDate = search.scraped_at || search.created_at;
    const scrapedDateFr = new Date(scrapedDate).toLocaleString('fr-FR', {
        day: 'numeric', month: 'short', year: 'numeric',
        hour: '2-digit', minute: '2-digit',
    });

    root.innerHTML = `
        <section class="search-detail">
            <a href="/hub" data-link class="back-link">← Retour au hub</a>

            <div class="search-header card">
                <div class="model-banner ${isCloud ? 'cloud' : 'local'}">
                    ${isCloud ? '✨' : '⚡'} ${escapeHtml(search.model_name)} — modèle ${isCloud ? 'cloud (précision élevée)' : 'local'}
                </div>
                <div class="search-header-body">
                    <h2>${escapeHtml(search.title)}</h2>
                    <div class="search-author">
                        ${avatarHtml(author, 32)}
                        ${author?.username
                            ? `<span>par <a href="/profile/${encodeURIComponent(author.username)}" data-link class="author-link"><strong>@${escapeHtml(author.username)}</strong></a></span>`
                            : `<span>par <strong>@?</strong></span>`}
                        <span class="muted">·</span>
                        <span class="muted">${platform}</span>
                        <span class="muted">·</span>
                        <span class="muted">scrapé le ${scrapedDateFr}</span>
                    </div>
                    ${search.criteria ? `<p class="search-criteria"><strong>Critères :</strong> ${escapeHtml(search.criteria)}</p>` : ''}
                    ${search.source_url ? `<p><a href="${search.source_url}" target="_blank" rel="noopener" class="muted-link">🔗 URL d'origine</a></p>` : ''}
                </div>
            </div>

            ${listings.length === 0 ? `
                <div class="empty-state card">
                    <h3>Pas d'annonce</h3>
                    <p>Cette recherche n'a aucune annonce publiée.</p>
                </div>
            ` : `
                <div class="search-controls card">
                    <input type="text" id="searchFilter" placeholder="🔍 Filtrer par titre / spec...">
                    <select id="searchSortBy">
                        <option value="note-desc">Meilleures notes ⭐</option>
                        <option value="price-asc">Prix croissant 📈</option>
                        <option value="price-desc">Prix décroissant 📉</option>
                    </select>
                    <select id="searchMinScore">
                        <option value="0">Toutes notes</option>
                        <option value="60">≥ 60/100</option>
                        <option value="75">≥ 75/100</option>
                        <option value="85">≥ 85/100</option>
                    </select>
                    <span class="search-controls-count" id="listingsCount"></span>
                </div>
                <div id="listingsGrid" class="grid-container"></div>
            `}
        </section>
    `;

    if (listings.length === 0) return;

    const filterEl   = document.getElementById('searchFilter');
    const sortByEl   = document.getElementById('searchSortBy');
    const minScoreEl = document.getElementById('searchMinScore');
    const gridEl     = document.getElementById('listingsGrid');
    const countEl    = document.getElementById('listingsCount');

    function renderListings() {
        const q = filterEl.value.toLowerCase().trim();
        const sortBy = sortByEl.value;
        const minScore = parseFloat(minScoreEl.value);

        let filtered = listings.filter(l => {
            const hay = ((l.titre || '') + ' ' + (l.caracteristiques || '')).toLowerCase();
            return hay.includes(q) && (parseFloat(l.note_sur_100) || 0) >= minScore;
        });

        if (sortBy === 'price-asc') {
            filtered.sort((a, b) => (a.prix ?? Infinity) - (b.prix ?? Infinity));
        } else if (sortBy === 'price-desc') {
            filtered.sort((a, b) => (b.prix ?? -Infinity) - (a.prix ?? -Infinity));
        } else {
            filtered.sort((a, b) => (b.note_sur_100 || 0) - (a.note_sur_100 || 0));
        }

        countEl.textContent = `${filtered.length} / ${listings.length} annonces`;

        gridEl.innerHTML = filtered.length === 0
            ? '<div class="empty-state card"><p>Aucune annonce ne correspond aux filtres.</p></div>'
            : filtered.map(listingCardHtml).join('');
    }

    filterEl.addEventListener('input', renderListings);
    sortByEl.addEventListener('change', renderListings);
    minScoreEl.addEventListener('change', renderListings);
    renderListings();
}
