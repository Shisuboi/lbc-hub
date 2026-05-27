// js/components/feed-card.js
// Carte de recherche affichée dans le feed /hub.
// Bandeau coloré = type de modèle (cloud violet / local gris).
import { avatarHtml } from '../lib/colors.js';

function escapeHtml(s) {
    if (s == null) return '';
    return String(s).replace(/[&<>"']/g, c => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[c]));
}

// Date affichée = scraped_at si présent, sinon created_at (fallback pour les
// premières searches insérées manuellement avant que scraped_at soit set).
function bestDate(search) {
    return search.scraped_at || search.created_at;
}

function dateFr(iso) {
    const d = new Date(iso);
    const diffMin = (Date.now() - d.getTime()) / 60000;
    if (diffMin < 1) return 'à l\'instant';
    if (diffMin < 60) return `il y a ${Math.floor(diffMin)} min`;
    if (diffMin < 1440) return `il y a ${Math.floor(diffMin / 60)} h`;
    const sameYear = d.getFullYear() === new Date().getFullYear();
    return d.toLocaleDateString('fr-FR', {
        day: 'numeric',
        month: 'short',
        ...(sameYear ? {} : { year: 'numeric' }),
    });
}

// Badge plateforme — décisions UX dans CLAUDE.md
const PLATFORM_BADGES = {
    leboncoin: { icon: '🟠', label: 'LBC' },
    ebay:      { icon: '🔵', label: 'eBay' },
    vinted:    { icon: '🟢', label: 'Vinted' },
    other:     { icon: '⚪', label: 'Autre' },
};

export function feedCardHtml(search, profile) {
    const isCloud = search.model_type === 'cloud';
    const banner = isCloud
        ? `<div class="model-banner cloud">✨ ${escapeHtml(search.model_name)} — modèle cloud (précision élevée)</div>`
        : `<div class="model-banner local">⚡ ${escapeHtml(search.model_name)} — modèle local</div>`;

    const platform = PLATFORM_BADGES[search.platform] || PLATFORM_BADGES.other;
    const platformBadge = `<span class="badge badge-platform">${platform.icon} ${platform.label}</span>`;

    return `
        <a href="/search/${search.id}" data-link data-search-id="${search.id}" class="feed-card card">
            ${banner}
            <div class="feed-card-meta">
                <div class="feed-author">
                    ${avatarHtml(profile, 28)}
                    <span class="feed-author-name">@${escapeHtml(profile?.username || '?')}</span>
                </div>
                <span class="feed-date">${dateFr(bestDate(search))}</span>
            </div>
            <h3 class="feed-title">${escapeHtml(search.title)}</h3>
            <div class="feed-badges">
                ${platformBadge}
                <span class="badge">${search.listing_count} annonces</span>
                ${search.best_score !== null && search.best_score !== undefined ? `<span class="badge badge-gold">⭐ ${Math.round(search.best_score)}/100</span>` : ''}
                ${search.min_price !== null && search.min_price !== undefined ? `<span class="badge badge-emerald">💰 ${Math.round(search.min_price)} €</span>` : ''}
            </div>
        </a>
    `;
}
