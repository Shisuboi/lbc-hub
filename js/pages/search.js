// js/pages/search.js
// Page /search/:id — détail d'une recherche publiée :
//   - bandeau modèle (cloud/local)
//   - méta : auteur, plateforme, date de scraping, URL source
//   - filtres : texte, score min, tri (note/prix)
//   - grille de listing cards
import { supa } from '../supabase-client.js';
import { requireAuth, getProfile } from '../auth.js';
import { listingCardHtml } from '../components/listing-card.js';
import { avatarHtml } from '../lib/colors.js';
import { loadFavorites, toggleFavorite, isFavorite } from '../lib/favorites.js';
import { navState } from '../router.js';

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
    const myToken = navState.token;
    await requireAuth();
    if (navState.token !== myToken) return;

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

    if (navState.token !== myToken) return;
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
    if (navState.token !== myToken) return;

    const me = await getProfile();
    if (navState.token !== myToken) return;
    await loadFavorites(me?.id);
    if (navState.token !== myToken) return;
    const fav = isFavorite(search.id);

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
                    ${isCloud ? '✨' : '⚡'} ${escapeHtml(search.model_name)} · modèle ${isCloud ? 'cloud (précision élevée)' : 'local'}
                </div>
                <div class="search-header-body">
                    <div class="search-title-row">
                        <h2>${escapeHtml(search.title)}</h2>
                        <div class="search-title-actions">
                            <button type="button" id="btnSearchFav" class="fav-btn fav-btn-lg ${fav ? 'is-fav' : ''}" title="${fav ? 'Retirer des favoris' : 'Ajouter aux favoris'}" aria-label="favori">${fav ? '⭐' : '☆'}</button>
                            ${(me?.id === search.user_id || me?.role === 'admin') ? `
                            <button type="button" id="btnDeleteSearch" class="btn btn-danger-sm" title="Supprimer cette recherche">🗑️ Supprimer</button>
                            ` : ''}
                        </div>
                    </div>
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

    // Bouton favori sur le header
    const btnFav = document.getElementById('btnSearchFav');
    if (btnFav && me?.id) {
        btnFav.addEventListener('click', async () => {
            if (btnFav.dataset.pending) return;
            const wasFav = isFavorite(search.id);
            const willBeFav = !wasFav;

            // Mise à jour optimiste — feedback immédiat
            btnFav.dataset.pending = '1';
            btnFav.classList.toggle('is-fav', willBeFav);
            btnFav.textContent = willBeFav ? '⭐' : '☆';
            btnFav.title = willBeFav ? 'Retirer des favoris' : 'Ajouter aux favoris';

            try {
                await toggleFavorite(me.id, search.id);
            } catch (err) {
                console.error('toggleFavorite failed', err);
                btnFav.classList.toggle('is-fav', wasFav);
                btnFav.textContent = wasFav ? '⭐' : '☆';
                btnFav.title = wasFav ? 'Retirer des favoris' : 'Ajouter aux favoris';
            } finally {
                delete btnFav.dataset.pending;
            }
        });
    }

    // Bouton suppression (owner ou admin seulement)
    const btnDelete = document.getElementById('btnDeleteSearch');
    if (btnDelete) {
        btnDelete.addEventListener('click', async () => {
            if (!confirm(`Supprimer définitivement "${search.title}" et toutes ses annonces ? Cette action est irréversible.`)) return;
            btnDelete.disabled = true;
            btnDelete.textContent = '⏳ Suppression…';
            const { error } = await supa.from('searches').delete().eq('id', search.id);
            if (error) {
                alert(`Erreur lors de la suppression : ${error.message}`);
                btnDelete.disabled = false;
                btnDelete.textContent = '🗑️ Supprimer';
            } else {
                window.history.pushState({}, '', '/lbc-hub/hub');
                window.dispatchEvent(new PopStateEvent('popstate'));
            }
        });
    }

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

    // === Toggle "annonce expirée" via délégation ===
    gridEl.addEventListener('click', async (e) => {
        const btn = e.target.closest('.expire-btn');
        if (!btn) return;
        const listingId = btn.dataset.expireId;
        const wasExpired = btn.dataset.expired === '1';
        const listing = listings.find(l => l.id === listingId);
        if (!listing) return;
        btn.disabled = true;
        const original = btn.innerHTML;
        btn.innerHTML = '⏳…';
        const newValue = wasExpired ? null : new Date().toISOString();
        // .select('id') force Prefer:return=representation (réponse 200 JSON)
        // au lieu du 204 No Content par défaut — le SDK résout plus fiablement.
        let error;
        try {
            ({ error } = await supa
                .from('listings')
                .update({ expired_at: newValue })
                .eq('id', listingId)
                .select('id'));
        } catch (err) {
            console.error('mark expired threw', err);
            btn.innerHTML = original;
            btn.disabled = false;
            alert('Erreur réseau : ' + err.message);
            return;
        }
        if (error) {
            console.error('mark expired failed', error);
            btn.innerHTML = original;
            btn.disabled = false;
            alert('Échec de la mise à jour : ' + error.message);
            return;
        }
        listing.expired_at = newValue;
        renderListings();
    });
}
