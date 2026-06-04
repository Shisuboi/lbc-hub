// js/lib/page-transition.js
// Splash de transition entre pages. À chaque navigation, un pictogramme animé propre
// à l'onglet de destination apparaît au centre, joue brièvement, puis l'ensemble
// grandit légèrement + se fond pour révéler la page (vie + impression de chargement).
//
// Pilotage : js/router.js appelle startTransition(path) avant de charger la page,
// puis endTransition() une fois la page prête. Un minimum forcé (MIN_MS) garantit que
// le splash se voit même si la page est déjà en cache.
//
// prefers-reduced-motion : aucun overlay (révélation instantanée).

const REDUCED = matchMedia('(prefers-reduced-motion: reduce)').matches;
const MIN_MS = 880;        // durée mini forcée : entrée douce + court temps de pose
const BOOK_MIN_MS = 1900;  // le livre du Journal joue une séquence complète (~1,9s) : on la laisse finir
const OUT_MS = 380;        // fondu de sortie (doux)

let overlay = null;
let startTs = 0;
let currentMin = MIN_MS;   // minimum d'affichage de la transition en cours (dépend du picto)

// Route → type d'animation (chaque onglet le sien)
function animFor(path) {
  if (path.startsWith('/feed')) return 'home';      // maison qui se dessine
  if (path.startsWith('/favorites')) return 'heart'; // cœur qui bat
  if (path.startsWith('/watchlist')) return 'ecg';   // cardiogramme qui court
  if (path.startsWith('/dashboard')) return 'book';  // livre du Journal qui se feuillette
  if (path.startsWith('/admin')) return 'faders';    // table de mixage
  if (path.startsWith('/profile')) return 'user';    // avatar qui se dessine
  return 'bolt';                                      // login, install, item… : éclair LBC
}

const SVGS = {
  ecg: `<svg viewBox="0 0 48 48" class="pfx-svg pfx-ecg" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
      <path pathLength="100" d="M3 24 H14 L19 12 L25 36 L30 20 L33 24 H45"/></svg>`,
  bars: `<svg viewBox="0 0 48 48" class="pfx-svg pfx-bars" fill="currentColor">
      <rect class="b b1" x="6"  y="10" width="7" height="28" rx="2.5"/>
      <rect class="b b2" x="16" y="10" width="7" height="28" rx="2.5"/>
      <rect class="b b3" x="26" y="10" width="7" height="28" rx="2.5"/>
      <rect class="b b4" x="36" y="10" width="7" height="28" rx="2.5"/></svg>`,
  faders: `<svg viewBox="0 0 48 48" class="pfx-svg pfx-faders" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round">
      <line x1="12" y1="7" x2="12" y2="41"/><line x1="24" y1="7" x2="24" y2="41"/><line x1="36" y1="7" x2="36" y2="41"/>
      <rect class="h h1" x="6"  y="21" width="12" height="6" rx="3" fill="currentColor" stroke="none"/>
      <rect class="h h2" x="18" y="21" width="12" height="6" rx="3" fill="currentColor" stroke="none"/>
      <rect class="h h3" x="30" y="21" width="12" height="6" rx="3" fill="currentColor" stroke="none"/></svg>`,
  home: `<svg viewBox="0 0 48 48" class="pfx-svg pfx-draw" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
      <path pathLength="100" d="M7 23 L24 8 L41 23"/><path pathLength="100" d="M11 20 V40 H37 V20"/></svg>`,
  heart: `<svg viewBox="0 0 48 48" class="pfx-svg pfx-heart" fill="currentColor">
      <path d="M24 41 L9.5 26.5 a8.4 8.4 0 0 1 12-11.9 l2.5 2.5 2.5-2.5 a8.4 8.4 0 0 1 12 11.9 z"/></svg>`,
  user: `<svg viewBox="0 0 48 48" class="pfx-svg pfx-draw" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
      <circle pathLength="100" cx="24" cy="17" r="8"/><path pathLength="100" d="M9 41 a15 15 0 0 1 30 0"/></svg>`,
  bolt: `<svg viewBox="0 0 48 48" class="pfx-svg pfx-bolt" fill="currentColor">
      <path d="M27 4 L10 27 h11 l-2 17 17-25 H32 l2-15 z"/></svg>`,
  // Journal : le livre se dessine (posé) → 5 pages se tournent en 3D (rafale) →
  // le livre se ferme (ralenti) ; le texte intérieur s'efface pendant la fermeture.
  book: `<svg viewBox="0 0 48 48" class="pfx-svg pfx-book" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
      <path class="draw-line left-page" d="M24 38 L4 38 L4 12 L24 12"/>
      <path class="draw-text left-text" d="M10 18 L18 18 M10 25 L18 25 M10 32 L14 32"/>
      <path class="draw-text right-static-text" d="M30 18 L38 18 M30 25 L38 25 M34 32 L38 32"/>
      <g class="close-book"><rect width="48" height="48" fill="none" stroke="none"/>
        <path class="draw-line right-page" d="M24 38 L44 38 L44 12 L24 12"/></g>
      <line class="draw-line binding" x1="24" y1="12" x2="24" y2="38"/>
      <g class="flip-page page-1"><rect width="48" height="48" fill="none" stroke="none"/><path d="M24 38 L44 38 L44 12 L24 12 M30 18 L38 18 M30 25 L38 25 M34 32 L38 32"/></g>
      <g class="flip-page page-2"><rect width="48" height="48" fill="none" stroke="none"/><path d="M24 38 L44 38 L44 12 L24 12 M30 18 L38 18 M30 25 L38 25 M34 32 L38 32"/></g>
      <g class="flip-page page-3"><rect width="48" height="48" fill="none" stroke="none"/><path d="M24 38 L44 38 L44 12 L24 12 M30 18 L38 18 M30 25 L38 25 M34 32 L38 32"/></g>
      <g class="flip-page page-4"><rect width="48" height="48" fill="none" stroke="none"/><path d="M24 38 L44 38 L44 12 L24 12 M30 18 L38 18 M30 25 L38 25 M34 32 L38 32"/></g>
      <g class="flip-page page-5"><rect width="48" height="48" fill="none" stroke="none"/><path d="M24 38 L44 38 L44 12 L24 12 M30 18 L38 18 M30 25 L38 25 M34 32 L38 32"/></g>
    </svg>`,
};

const sleep = ms => new Promise(r => setTimeout(r, ms));
function destroy() { if (overlay) { overlay.remove(); overlay = null; } }

// Démarre le splash pour la route de destination. Idempotent : remplace tout splash en cours.
export function startTransition(path) {
  destroy();
  if (REDUCED) return;
  const type = animFor(path || '/');
  // Le livre a une séquence non bouclée (dessin → pages → fermeture) : on lui laisse
  // le temps de la jouer entièrement. Les autres pictos bouclent → 880 ms suffisent.
  currentMin = (type === 'book') ? BOOK_MIN_MS : MIN_MS;
  overlay = document.createElement('div');
  overlay.className = 'pagefx';
  overlay.setAttribute('aria-hidden', 'true');
  overlay.innerHTML = `<div class="pagefx-badge">${SVGS[type] || SVGS.bolt}</div>`;
  // Injecté DANS .app-container (et non body) pour rester dans le même contexte
  // d'empilement que le dock/rail → ceux-ci restent au-dessus (z 60 / 50 > 40) et
  // cliquables pendant le chargement. Sibling de #appRoot → survit au swap de page.
  (document.querySelector('.app-container') || document.body).appendChild(overlay);
  void overlay.offsetWidth;          // reflow → l'anim d'entrée part proprement
  overlay.classList.add('pagefx-in');
  startTs = performance.now();
}

// Termine le splash : attend la durée mini, joue la sortie (grandit + fond), puis retire.
export async function endTransition() {
  if (!overlay) return;
  const el = overlay;
  overlay = null;                    // libère le module pour une éventuelle nav suivante
  const remaining = currentMin - (performance.now() - startTs);
  if (remaining > 0) await sleep(remaining);
  el.classList.add('pagefx-out');
  await sleep(OUT_MS);
  el.remove();
}
