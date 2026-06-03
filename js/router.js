// js/router.js
// Mini-router history API. Routes statiques + paramètres dynamiques (:id, :token, :username).
// En prod GitHub Pages, l'URL est préfixée par /lbc-hub (= nom du repo) : on strip ce prefix
// avant de matcher pour que les définitions de routes restent identiques en dev et en prod.
import { startTransition, endTransition } from './lib/page-transition.js';

const ROUTE_PREFIX = '/lbc-hub';
const routes = [];
let notFoundHandler = null;

// Token incrémenté à chaque navigation. Exporté pour que les loaders de pages
// puissent vérifier s'ils sont toujours la navigation active avant chaque écriture DOM.
export const navState = { token: 0 };

export function route(pattern, loader) {
    // pattern: '/hub' ou '/search/:id'
    const paramNames = [];
    const regex = new RegExp('^' + pattern.replace(/:([a-zA-Z]+)/g, (_, name) => {
        paramNames.push(name);
        return '([^/]+)';
    }) + '$');
    routes.push({ pattern, regex, paramNames, loader });
}

export function notFound(loader) {
    notFoundHandler = loader;
}

function stripPrefix(path) {
    if (path.startsWith(ROUTE_PREFIX)) {
        const rest = path.slice(ROUTE_PREFIX.length);
        return rest === '' ? '/' : rest;
    }
    return path;
}

export async function navigate(path, replace = false) {
    // Quand on navigue, on ré-ajoute le prefix si nécessaire (pour que l'URL affichée reste correcte)
    const needsPrefix = location.pathname.startsWith(ROUTE_PREFIX) && !path.startsWith(ROUTE_PREFIX);
    const finalPath = needsPrefix ? ROUTE_PREFIX + path : path;
    if (replace) history.replaceState({}, '', finalPath);
    else history.pushState({}, '', finalPath);
    await render();
}

export async function render() {
    const myToken = ++navState.token;
    const path = stripPrefix(location.pathname) || '/';
    const root = document.getElementById('appRoot');
    window.scrollTo(0, 0); // Remonte en haut à chaque changement de page
    // Notifie le chrome (rail + dock) pour resynchroniser l'état actif selon l'URL.
    window.dispatchEvent(new CustomEvent('spa:navigated', { detail: { path } }));
    // Splash de transition (picto animé propre à l'onglet) — révélé par endTransition().
    startTransition(path);
    for (const r of routes) {
        const m = path.match(r.regex);
        if (m) {
            const params = {};
            r.paramNames.forEach((name, i) => {
                params[name] = decodeURIComponent(m[i + 1]);
            });
            root.innerHTML = '<div class="page-loading"></div>';
            try {
                await r.loader(params);
            } catch (e) {
                if (e && e.message === 'Not authenticated') return; // requireAuth a déjà redirigé (la nouvelle nav reprend le splash)
                if (e && e.message === 'Profile not yet created') return;
                // Une navigation plus récente a démarré pendant qu'on chargeait : on abandonne
                // silencieusement pour ne pas écraser la nouvelle page avec un panel d'erreur.
                if (myToken !== navState.token) return;
                console.error('[router] page load failed', e);
                root.innerHTML = `<div class="error-panel card">❌ Erreur de chargement : ${e.message}</div>`;
            }
            // Termine le splash UNIQUEMENT si on est encore la navigation active
            // (sinon une nav plus récente a déjà repris la main sur l'overlay).
            if (myToken === navState.token) await endTransition();
            return;
        }
    }
    if (notFoundHandler) await notFoundHandler();
    if (myToken === navState.token) await endTransition();
}

export function init() {
    window.addEventListener('popstate', () => { render(); });
    // Intercept tous les clics sur <a data-link> pour navigation SPA
    document.body.addEventListener('click', e => {
        const a = e.target.closest('a[data-link]');
        if (a) {
            e.preventDefault();
            const href = a.getAttribute('href');
            navigate(href);
        }
    });
    render();
}
