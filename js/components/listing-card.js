// js/components/listing-card.js
// Carte d'une annonce dans la page /search/:id.
// Réutilise les classes CSS existantes du scraper (card-top, card-score, etc.)
// pour ne pas dupliquer les styles.

function escapeHtml(s) {
    if (s == null) return '';
    return String(s).replace(/[&<>"']/g, c => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[c]));
}

function escapeAttr(s) {
    return escapeHtml(s);
}

function scoreClassFor(note) {
    const n = parseFloat(note) || 0;
    if (n >= 80) return 'score-high';
    if (n >= 60) return 'score-medium';
    return 'score-low';
}

export function listingCardHtml(listing) {
    const note = parseFloat(listing.note_sur_100) || 0;
    const scoreClass = scoreClassFor(note);
    const prix = listing.prix != null ? `${Math.round(listing.prix)} €` : 'N/A';
    const matchIcon = listing.match_criteres ? '✅' : '⚠️';

    return `
        <div class="result-card">
            <div class="card-top">
                <div class="card-price">${prix}</div>
                <div class="card-score ${scoreClass}">${matchIcon} ${Math.round(note)}/100</div>
            </div>
            <div class="card-title" title="${escapeAttr(listing.titre || '')}">${escapeHtml(listing.titre || '')}</div>
            ${listing.caracteristiques ? `
                <div class="card-tags">
                    <span class="card-tag">🔍 ${escapeHtml(listing.caracteristiques)}</span>
                </div>` : ''}
            ${listing.explication ? `
                <div class="card-analysis">
                    <span class="analysis-label">🤖 Justification IA</span>
                    ${escapeHtml(listing.explication)}
                </div>` : ''}
            ${listing.url ? `<a href="${listing.url}" target="_blank" rel="noopener" class="btn-card">Voir l'annonce 🔗</a>` : ''}
        </div>
    `;
}
