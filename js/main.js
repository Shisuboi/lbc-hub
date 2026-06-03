// js/main.js
// Entrypoint SPA : déclare les routes (lazy-loaded), rend le header, démarre le router.
import { route, notFound, init as initRouter } from './router.js';
import { renderHeader } from './components/header.js';
import { onAuthChange } from './supabase-client.js';
import { initLiquidGlass } from './lib/liquid-glass.js';

// === ROUTES ===
// Chaque page est lazy-loaded pour limiter le bundle initial.
route('/',                  () => import('./pages/login.js').then(m => m.render()));
route('/install',           () => import('./pages/install.js').then(m => m.render()));
route('/invite/:token',     (p) => import('./pages/invite.js').then(m => m.render(p)));
route('/onboarding',        () => import('./pages/invite.js').then(m => m.renderOnboarding()));
route('/feed',              () => import('./pages/feed.js').then(m => m.render()));
route('/favorites',         () => import('./pages/favorites.js').then(m => m.render()));
route('/item/:id',          (p) => import('./pages/item.js').then(m => m.render(p)));
route('/watchlist',         () => import('./pages/watchlist.js').then(m => m.render()));
route('/dashboard',         () => import('./pages/dashboard.js').then(m => m.render()));
route('/profile/:username', (p) => import('./pages/profile.js').then(m => m.render(p)));
route('/admin',             () => import('./pages/admin.js').then(m => m.render()));

notFound(async () => {
    document.getElementById('appRoot').innerHTML = `
        <div class="error-panel card">
            <h2>Page introuvable</h2>
            <a href="/feed" data-link class="btn btn-primary">Retour au feed</a>
        </div>`;
});

// Thème clair « Apple Liquid Glass » scopé aux pages flux (feed / favoris / item).
// Les autres pages restent en sombre immersif tant qu'elles ne sont pas redessinées.
// Doit être enregistré AVANT initRouter() : initRouter() rend immédiatement et émet
// l'event 'spa:navigated' sur lequel on s'appuie pour fixer le thème du 1er rendu.
const LIGHT_ROUTES = [/^\/feed$/, /^\/favorites$/, /^\/item\//];
window.addEventListener('spa:navigated', e => {
    const path = e.detail?.path || '/';
    if (LIGHT_ROUTES.some(re => re.test(path))) document.documentElement.dataset.theme = 'light';
    else delete document.documentElement.dataset.theme; // fallback :root (sombre)
});

initLiquidGlass();
await renderHeader();
initRouter();

// Re-render header à chaque changement d'auth (login / logout / refresh token).
// IMPORTANT : enregistré APRÈS le premier rendu pour éviter un deadlock du SDK
// (l'event INITIAL_SESSION rentrait sur le lock interne pendant le boot).
onAuthChange(() => renderHeader());
