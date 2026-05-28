// js/pages/admin.js
// Page /admin : gestion des invitations (réservée au rôle admin).
// L'admin peut générer un nouveau token et copier l'URL d'invitation
// formatée pour son ami. Il peut aussi voir les invitations existantes.
//
// Limite Phase 1.5 : la création du user auth elle-même se fait toujours
// manuellement dans le Supabase Dashboard (nécessite la service_role qu'on
// ne peut pas exposer en frontend). L'admin doit donc faire :
//   1) Créer le user auth dans Supabase Dashboard (email + mdp temp)
//   2) Générer un lien d'invitation ici
//   3) Envoyer au pote l'URL + ses identifiants

import { supa } from '../supabase-client.js';
import { requireAuth, getProfile } from '../auth.js';

const SITE_URL = `${location.origin}${location.pathname.startsWith('/lbc-hub') ? '/lbc-hub' : ''}`;

export async function render() {
    await requireAuth({ requireRole: 'admin' });
    const me = await getProfile();

    const root = document.getElementById('appRoot');
    root.innerHTML = `
        <section class="admin-page">
            <div class="admin-header">
                <h2>🛠️ Administration</h2>
                <p class="muted">Connecté en tant que <strong>@${me.username}</strong> (admin)</p>
            </div>

            <div class="admin-card card">
                <h3>📨 Inviter un ami</h3>
                <ol class="admin-steps">
                    <li>
                        <strong>Crée son compte auth</strong> dans le
                        <a href="https://supabase.com/dashboard/project/pfkuphmpzhdmfwaifywj/auth/users" target="_blank" rel="noopener">Supabase Dashboard</a>
                        (bouton "Add user" → email + mdp temporaire + ✅ Auto Confirm Email).
                    </li>
                    <li>
                        <strong>Génère un lien d'invitation</strong> ci-dessous, puis envoie-lui l'URL + ses identifiants.
                    </li>
                </ol>
                <button id="btnGenerate" class="btn btn-primary">✨ Générer un lien d'invitation</button>
                <div id="genResult" class="gen-result hidden"></div>
            </div>

            <div class="admin-card card">
                <h3>📜 Invitations existantes</h3>
                <div id="invitationsTable" class="invitations-table">
                    <p class="muted">Chargement…</p>
                </div>
            </div>
        </section>
    `;

    document.getElementById('btnGenerate').addEventListener('click', generateInvitation);
    await loadInvitations();
}

async function generateInvitation() {
    const btn = document.getElementById('btnGenerate');
    const resultEl = document.getElementById('genResult');
    btn.disabled = true;
    btn.textContent = '⏳ Génération…';

    const { data, error } = await supa.from('invitations').insert({}).select().single();

    btn.disabled = false;
    btn.innerHTML = '✨ Générer un lien d\'invitation';

    if (error) {
        resultEl.classList.remove('hidden');
        resultEl.className = 'gen-result error';
        resultEl.textContent = `❌ ${error.message}`;
        return;
    }

    const url = `${SITE_URL}/invite/${data.token}`;
    const expiresAt = new Date(data.expires_at).toLocaleString('fr-FR');
    resultEl.classList.remove('hidden');
    resultEl.className = 'gen-result success';
    resultEl.innerHTML = `
        <p>✅ Invitation créée — expire le ${expiresAt}</p>
        <div class="copy-row">
            <input type="text" id="inviteUrlInput" value="${url}" readonly>
            <button id="btnCopy" class="btn btn-secondary">📋 Copier</button>
        </div>
        <p class="muted small">Envoie cette URL + l'email/mdp temporaire que tu as créés dans Supabase à ton ami.</p>
    `;

    document.getElementById('btnCopy').addEventListener('click', async () => {
        const input = document.getElementById('inviteUrlInput');
        input.select();
        try {
            await navigator.clipboard.writeText(input.value);
            document.getElementById('btnCopy').textContent = '✅ Copié !';
            setTimeout(() => {
                const b = document.getElementById('btnCopy');
                if (b) b.textContent = '📋 Copier';
            }, 2000);
        } catch (_) {
            // Fallback : sélection seulement
        }
    });

    // Refresh la liste
    await loadInvitations();
}

async function loadInvitations() {
    const container = document.getElementById('invitationsTable');
    const { data: invitations, error } = await supa
        .from('invitations')
        .select('token, used_by, used_at, expires_at, created_at')
        .order('created_at', { ascending: false })
        .limit(30);

    if (error) {
        container.innerHTML = `<p class="error">Erreur de chargement : ${error.message}</p>`;
        return;
    }

    if (!invitations || invitations.length === 0) {
        container.innerHTML = '<p class="muted">Aucune invitation pour le moment.</p>';
        return;
    }

    // Fetch les profils des users qui ont consommé des invitations
    const usedByIds = [...new Set(invitations.map(i => i.used_by).filter(Boolean))];
    let profileMap = new Map();
    if (usedByIds.length) {
        const { data: profiles } = await supa
            .from('profiles')
            .select('id, username')
            .in('id', usedByIds);
        profileMap = new Map((profiles || []).map(p => [p.id, p]));
    }

    const now = Date.now();
    const rows = invitations.map(inv => {
        const tokenShort = inv.token.slice(0, 8) + '…' + inv.token.slice(-4);
        let status, statusClass;
        if (inv.used_at) {
            const profile = profileMap.get(inv.used_by);
            status = `Utilisée par @${profile?.username || '?'}`;
            statusClass = 'status-used';
        } else if (new Date(inv.expires_at).getTime() < now) {
            status = 'Expirée';
            statusClass = 'status-expired';
        } else {
            status = 'Active';
            statusClass = 'status-active';
        }
        const createdAt = new Date(inv.created_at).toLocaleString('fr-FR');
        const expiresAt = new Date(inv.expires_at).toLocaleString('fr-FR');
        return `
            <tr>
                <td><code>${tokenShort}</code></td>
                <td>${createdAt}</td>
                <td>${expiresAt}</td>
                <td><span class="status-badge ${statusClass}">${status}</span></td>
            </tr>
        `;
    }).join('');

    container.innerHTML = `
        <table class="invitations-list">
            <thead>
                <tr>
                    <th>Token</th>
                    <th>Créée</th>
                    <th>Expire</th>
                    <th>Statut</th>
                </tr>
            </thead>
            <tbody>${rows}</tbody>
        </table>
    `;
}
