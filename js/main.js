// js/main.js
// Entrypoint SPA : déclare les routes (lazy-loaded), rend le header, démarre le router.
console.log('[main] start');
import { route, notFound, init as initRouter } from './router.js';
import { renderHeader } from './components/header.js';
import { onAuthChange } from './supabase-client.js';
console.log('[main] imports OK');

// === ROUTES ===
// Chaque page est lazy-loaded pour limiter le bundle initial.
route('/',                  () => import('./pages/login.js').then(m => m.render()));
route('/install',           () => import('./pages/install.js').then(m => m.render()));
route('/invite/:token',     (p) => import('./pages/invite.js').then(m => m.render(p)));
route('/onboarding',        () => import('./pages/invite.js').then(m => m.renderOnboarding()));
route('/hub',               () => import('./pages/hub.js').then(m => m.render()));
route('/scraper',           () => import('./pages/scraper.js').then(m => m.render()));
route('/search/:id',        (p) => import('./pages/search.js').then(m => m.render(p)));

notFound(async () => {
    document.getElementById('appRoot').innerHTML = `
        <div class="error-panel card">
            <h2>Page introuvable</h2>
            <a href="/hub" data-link class="btn btn-primary">Retour au Hub</a>
        </div>`;
});

console.log('[main] before renderHeader, location.pathname =', location.pathname);
await renderHeader();
console.log('[main] after renderHeader, before initRouter');
initRouter();
console.log('[main] after initRouter');

// Re-render header à chaque changement d'auth (login / logout / refresh token)
// Enregistré APRÈS le premier rendu pour éviter un éventuel deadlock SDK au boot.
onAuthChange(() => renderHeader());
