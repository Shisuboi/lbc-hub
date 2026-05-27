// js/pages/login.js
import { loginWithPassword } from '../auth.js';
import { supa } from '../supabase-client.js';
import { navigate } from '../router.js';

export async function render() {
    // Si déjà connecté → redirige vers /hub
    const { data: { user } } = await supa.auth.getUser();
    if (user) { navigate('/hub', true); return; }

    document.getElementById('appRoot').innerHTML = `
        <section class="auth-panel">
            <div class="auth-card card">
                <h2>Connexion</h2>
                <p class="muted">Plateforme privée — inscription sur invitation uniquement.</p>
                <form id="loginForm" class="auth-form">
                    <div class="form-group">
                        <label for="emailInput">Email</label>
                        <input type="email" id="emailInput" required autocomplete="email">
                    </div>
                    <div class="form-group">
                        <label for="passwordInput">Mot de passe</label>
                        <input type="password" id="passwordInput" required autocomplete="current-password">
                    </div>
                    <button type="submit" class="btn btn-primary">Se connecter</button>
                    <div id="loginError" class="form-error hidden"></div>
                </form>
                <p class="auth-footer">Besoin d'aide ? <a href="/install" data-link>Guide d'installation</a></p>
            </div>
        </section>
    `;

    document.getElementById('loginForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        const email = document.getElementById('emailInput').value.trim();
        const password = document.getElementById('passwordInput').value;
        const errorEl = document.getElementById('loginError');
        errorEl.classList.add('hidden');
        try {
            await loginWithPassword(email, password);
            // S'il y a un token d'invitation en attente, on redirige vers /invite
            const pending = sessionStorage.getItem('pendingInvite');
            if (pending) {
                navigate(`/invite/${pending}`);
            } else {
                navigate('/hub');
            }
        } catch (err) {
            errorEl.textContent = err.message === 'Invalid login credentials'
                ? 'Email ou mot de passe incorrect'
                : err.message;
            errorEl.classList.remove('hidden');
        }
    });
}
