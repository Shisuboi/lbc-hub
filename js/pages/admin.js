// js/pages/admin.js
// Page /admin : réservée au rôle admin.
// Depuis v1.8.0, le flow d'invitation par token est remplacé par du self-service
// onboarding (l'invité choisit son pseudo au 1er login). L'admin n'a donc plus
// qu'à créer le user auth dans Supabase Dashboard et envoyer les identifiants.
//
// Le RPC consume_invitation et la route /invite/:token sont conservés pour la
// rétro-compat des liens déjà envoyés, mais ne sont plus exposés ici.

import { requireAuth, getProfile } from '../auth.js';

const DASHBOARD_USERS_URL = 'https://supabase.com/dashboard/project/pfkuphmpzhdmfwaifywj/auth/users';

export async function render() {
    await requireAuth({ requireRole: 'admin' });
    const me = await getProfile();

    document.getElementById('appRoot').innerHTML = `
        <section class="admin-page">
            <div class="admin-header">
                <h2>🛠️ Administration</h2>
                <p class="muted">Connecté en tant que <strong>@${me.username}</strong> (admin)</p>
            </div>

            <div class="admin-card card">
                <h3>📨 Inviter un ami</h3>
                <p>Plus besoin de générer un lien d'invitation : ton pote choisit son pseudo lui-même au premier login.</p>
                <ol class="admin-steps">
                    <li>
                        Ouvre le <a href="${DASHBOARD_USERS_URL}" target="_blank" rel="noopener">Supabase Dashboard → Auth → Users</a>, clique <strong>Add user</strong>.
                    </li>
                    <li>
                        Renseigne :
                        <ul>
                            <li>Email : <code>prenom@lbc-hub.local</code> (pas besoin d'un vrai email)</li>
                            <li>Mot de passe temporaire (qu'il pourra changer plus tard)</li>
                            <li>✅ <strong>Auto Confirm Email</strong></li>
                        </ul>
                    </li>
                    <li>
                        Envoie-lui par message :
                        <ul>
                            <li>L'URL du hub : <code>${location.origin}${location.pathname.startsWith('/lbc-hub') ? '/lbc-hub' : ''}/</code></li>
                            <li>Son identifiant (<code>prenom</code> suffit, le domaine est ajouté automatiquement)</li>
                            <li>Son mdp temporaire</li>
                        </ul>
                    </li>
                </ol>
                <p class="muted small">Au 1er login, il sera invité à choisir son pseudo public — il atterrit direct sur le hub ensuite.</p>
            </div>
        </section>
    `;
}
