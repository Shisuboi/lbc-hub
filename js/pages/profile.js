// js/pages/profile.js
// Page /profile/:username — fiche publique d'un user du hub.
// Affiche l'avatar, le pseudo, le rôle, la date d'inscription,
// et la liste des recherches qu'il a publiées.

import { supa } from '../supabase-client.js';
import { requireAuth } from '../auth.js';
import { feedCardHtml } from '../components/feed-card.js';
import { avatarHtml } from '../lib/colors.js';
import { navState } from '../router.js';

function escapeHtml(s) {
    if (s == null) return '';
    return String(s).replace(/[&<>"']/g, c => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[c]));
}

function dateFr(iso) {
    const d = new Date(iso);
    return d.toLocaleDateString('fr-FR', {
        day: 'numeric', month: 'long', year: 'numeric',
    });
}

export async function render({ username }) {
    const myToken = navState.token;
    await requireAuth();
    if (navState.token !== myToken) return;

    const root = document.getElementById('appRoot');
    const cleanUsername = (username || '').trim().toLowerCase();

    if (!cleanUsername) {
        root.innerHTML = `
            <section class="profile-page">
                <div class="error-panel card">
                    <h2>Pseudo manquant</h2>
                    <a href="/hub" data-link class="btn btn-primary">Retour au Hub</a>
                </div>
            </section>`;
        return;
    }

    root.innerHTML = `<div class="page-loading">⏳ Chargement du profil…</div>`;

    // === Fetch profil ===
    const { data: profile, error: pErr } = await supa
        .from('profiles')
        .select('id, username, avatar_color, role, created_at')
        .eq('username', cleanUsername)
        .single();

    if (navState.token !== myToken) return;
    if (pErr || !profile) {
        root.innerHTML = `
            <section class="profile-page">
                <div class="error-panel card">
                    <h2>Profil introuvable</h2>
                    <p class="muted">Aucun membre nommé <code>@${escapeHtml(cleanUsername)}</code> sur ce hub.</p>
                    <a href="/hub" data-link class="btn btn-primary">Retour au Hub</a>
                </div>
            </section>`;
        return;
    }

    // === Fetch ses searches ===
    const { data: searches } = await supa
        .from('searches')
        .select('id, user_id, title, platform, model_name, model_type, listing_count, best_score, min_price, scraped_at, created_at')
        .eq('user_id', profile.id)
        .order('created_at', { ascending: false })
        .limit(100);

    if (navState.token !== myToken) return;
    const searchList = searches || [];

    // === Statistiques rapides ===
    const totalSearches = searchList.length;
    const totalListings = searchList.reduce((sum, s) => sum + (s.listing_count || 0), 0);
    const bestScore = searchList.reduce((max, s) => Math.max(max, s.best_score || 0), 0);
    const lastActivity = searchList.length
        ? (searchList[0].scraped_at || searchList[0].created_at)
        : null;

    // === Render ===
    const roleBadge = profile.role === 'admin'
        ? `<span class="badge badge-gold">🛠️ Admin</span>`
        : '';

    root.innerHTML = `
        <section class="profile-page">
            <a href="/hub" data-link class="back-link">← Retour au hub</a>

            <header class="profile-header card">
                <div class="profile-identity">
                    ${avatarHtml(profile, 72)}
                    <div class="profile-name-block">
                        <h1>@${escapeHtml(profile.username)} ${roleBadge}</h1>
                        <p class="muted">Membre depuis le ${dateFr(profile.created_at)}</p>
                    </div>
                </div>
                <div class="profile-stats">
                    <div class="profile-stat">
                        <span class="profile-stat-value">${totalSearches}</span>
                        <span class="profile-stat-label">Recherche${totalSearches > 1 ? 's' : ''} publiée${totalSearches > 1 ? 's' : ''}</span>
                    </div>
                    <div class="profile-stat">
                        <span class="profile-stat-value">${totalListings}</span>
                        <span class="profile-stat-label">Annonce${totalListings > 1 ? 's' : ''} analysée${totalListings > 1 ? 's' : ''}</span>
                    </div>
                    <div class="profile-stat">
                        <span class="profile-stat-value text-gold">${bestScore ? Math.round(bestScore) + '/100' : '·'}</span>
                        <span class="profile-stat-label">Meilleure note</span>
                    </div>
                    <div class="profile-stat">
                        <span class="profile-stat-value">${lastActivity ? dateFr(lastActivity) : '·'}</span>
                        <span class="profile-stat-label">Dernière activité</span>
                    </div>
                </div>
            </header>

            <h2 class="profile-section-title">📂 Ses recherches</h2>
            ${searchList.length === 0
                ? `<div class="empty-state card">
                       <p class="muted">@${escapeHtml(profile.username)} n'a encore rien publié sur le hub.</p>
                   </div>`
                : `<div class="feed-grid">${searchList.map(s => feedCardHtml(s, profile)).join('')}</div>`
            }
        </section>
    `;
}
