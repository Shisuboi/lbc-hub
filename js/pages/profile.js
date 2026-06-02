// js/pages/profile.js
// Page /profile/:username — fiche publique Phase C : identité + derniers commentaires.
// (L'ancien modèle "recherches publiées" a été retiré en C-5.)

import { supa } from '../supabase-client.js';
import { requireAuth } from '../auth.js';
import { avatarHtml } from '../lib/colors.js';
import { listCommentsByUser } from '../lib/comments.js';
import { navState } from '../router.js';

function escapeHtml(s) {
    if (s == null) return '';
    return String(s).replace(/[&<>"']/g, c => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[c]));
}

function dateFr(iso) {
    const d = new Date(iso);
    return d.toLocaleDateString('fr-FR', { day: 'numeric', month: 'long', year: 'numeric' });
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
                    <a href="/feed" data-link class="btn btn-primary">Retour au feed</a>
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
                    <a href="/feed" data-link class="btn btn-primary">Retour au feed</a>
                </div>
            </section>`;
        return;
    }

    // === Fetch ses derniers commentaires ===
    let comments = [];
    try { comments = await listCommentsByUser(profile.id, 20); } catch (_) {}
    if (navState.token !== myToken) return;

    const roleBadge = profile.role === 'admin'
        ? `<span class="badge badge-gold">🛠️ Admin</span>`
        : '';

    const commentsHtml = comments.length === 0
        ? `<div class="empty-state card">
               <p class="muted">@${escapeHtml(profile.username)} n'a encore rien commenté.</p>
           </div>`
        : `<div class="profile-comments">${comments.map(c => `
            <a href="/item/${c.opportunity_id}" data-link class="profile-comment card">
                <div class="pc-on muted">Sur « ${escapeHtml(c.opportunity?.title || 'une opportunité')} »</div>
                <div class="pc-body">${escapeHtml(c.body)}</div>
                <div class="pc-date muted">${dateFr(c.created_at)}</div>
            </a>`).join('')}</div>`;

    root.innerHTML = `
        <section class="profile-page">
            <a href="/feed" data-link class="back-link">← Retour au feed</a>

            <header class="profile-header card">
                <div class="profile-identity">
                    ${avatarHtml(profile, 72)}
                    <div class="profile-name-block">
                        <h1>@${escapeHtml(profile.username)} ${roleBadge}</h1>
                        <p class="muted">Membre depuis le ${dateFr(profile.created_at)}</p>
                    </div>
                </div>
            </header>

            <h2 class="profile-section-title">💬 Ses derniers commentaires</h2>
            ${commentsHtml}
        </section>
    `;
}
