// js/pages/invite.js
// Flow d'invitation :
//   1. L'admin a créé le user auth + une invitation (token). Il communique
//      l'URL /invite/:token + le mdp temporaire à l'invité.
//   2. L'invité ouvre l'URL → s'il n'est pas loggé, on stocke le token en
//      sessionStorage et on redirige vers /. Après login il reviendra ici.
//   3. L'invité authentifié choisit son pseudo (RPC consume_invitation),
//      le profil est créé, puis on l'envoie sur /hub.

import { supa } from '../supabase-client.js';
import { navigate } from '../router.js';
import { getProfile } from '../auth.js';

export async function render({ token }) {
    const { data: { session } } = await supa.auth.getSession();
    const user = session?.user;
    if (!user) {
        sessionStorage.setItem('pendingInvite', token);
        navigate('/', true);
        return;
    }

    // Valider le token avant d'afficher le formulaire
    const { data: validation, error: valError } = await supa.rpc('validate_invitation', {
        invitation_token: token,
    });
    if (valError) {
        document.getElementById('appRoot').innerHTML = `
            <section class="auth-panel">
                <div class="auth-card card">
                    <h2>❌ Erreur</h2>
                    <p>${valError.message}</p>
                </div>
            </section>`;
        return;
    }
    const result = Array.isArray(validation) ? validation[0] : validation;
    if (!result || !result.valid) {
        document.getElementById('appRoot').innerHTML = `
            <section class="auth-panel">
                <div class="auth-card card">
                    <h2>❌ Invitation invalide</h2>
                    <p>${result?.message || 'Token introuvable'}</p>
                    <a href="/hub" data-link class="btn">Retour</a>
                </div>
            </section>`;
        return;
    }

    // Si l'user a déjà un profil, l'invitation n'a plus de sens → vers /hub
    const profile = await getProfile(true);
    if (profile) { navigate('/hub', true); return; }

    document.getElementById('appRoot').innerHTML = `
        <section class="auth-panel">
            <div class="auth-card card">
                <h2>Bienvenue !</h2>
                <p class="muted">Choisis ton pseudo public (3-24 caractères, lettres minuscules, chiffres et _).</p>
                <form id="onboardForm" class="auth-form">
                    <div class="form-group">
                        <label for="usernameInput">Pseudo</label>
                        <input type="text" id="usernameInput" required pattern="[a-z0-9_]{3,24}" placeholder="alex_42">
                    </div>
                    <button type="submit" class="btn btn-primary">Créer mon profil</button>
                    <div id="onboardError" class="form-error hidden"></div>
                </form>
            </div>
        </section>`;

    document.getElementById('onboardForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        const username = document.getElementById('usernameInput').value.trim().toLowerCase();
        const errorEl = document.getElementById('onboardError');
        errorEl.classList.add('hidden');
        const { error } = await supa.rpc('consume_invitation', {
            invitation_token: token,
            new_username: username,
        });
        if (error) {
            errorEl.textContent = error.message.includes('unique') || error.message.includes('duplicate')
                ? 'Ce pseudo est déjà pris'
                : error.message;
            errorEl.classList.remove('hidden');
            return;
        }
        sessionStorage.removeItem('pendingInvite');
        navigate('/hub');
    });
}

export async function renderOnboarding() {
    // /onboarding = page d'atterrissage au 1er login (user auth créé par
    // l'admin dans Supabase Dashboard, mais profil pas encore créé).
    // Self-service : choisit son pseudo, on appelle create_self_profile.
    // Rétro-compat : si un token d'invitation est en sessionStorage, on
    // le respecte (flow legacy /invite/:token).
    const token = sessionStorage.getItem('pendingInvite');
    if (token) {
        navigate(`/invite/${token}`, true);
        return;
    }

    // Si l'user a déjà un profil (rare : arrivé là par erreur), → /hub
    const { data: { session } } = await supa.auth.getSession();
    if (!session?.user) { navigate('/', true); return; }
    const existing = await getProfile(true);
    if (existing) { navigate('/hub', true); return; }

    document.getElementById('appRoot').innerHTML = `
        <section class="auth-panel">
            <div class="auth-card card">
                <h2>Bienvenue !</h2>
                <p class="muted">Choisis ton pseudo public (3-24 caractères, lettres minuscules, chiffres et _).</p>
                <form id="onboardForm" class="auth-form">
                    <div class="form-group">
                        <label for="usernameInput">Pseudo</label>
                        <input type="text" id="usernameInput" required pattern="[a-z0-9_]{3,24}" placeholder="alex_42" autocomplete="off">
                    </div>
                    <button type="submit" class="btn btn-primary">Créer mon profil</button>
                    <div id="onboardError" class="form-error hidden"></div>
                </form>
            </div>
        </section>`;

    document.getElementById('onboardForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        const username = document.getElementById('usernameInput').value.trim().toLowerCase();
        const errorEl = document.getElementById('onboardError');
        errorEl.classList.add('hidden');
        const { error } = await supa.rpc('create_self_profile', { new_username: username });
        if (error) {
            errorEl.textContent = error.message.includes('unique') || error.message.includes('duplicate')
                ? 'Ce pseudo est déjà pris'
                : error.message;
            errorEl.classList.remove('hidden');
            return;
        }
        navigate('/hub');
    });
}
