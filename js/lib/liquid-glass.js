// js/lib/liquid-glass.js
// Moteur Liquid Glass réactif (vanilla, sans dépendance) — approximation web du
// matériau « Liquid Glass » d'Apple (iOS 26 / macOS 26).
//
// Mécanisme central : RÉFRACTION DE BORD via une displacement map en « biseau
// arrondi » (rounded-rect SDF), pas du bruit. La map encode un déplacement nul
// au centre (128,128) qui croît vers les bords → feDisplacementMap (#lg-disp dans
// index.html) courbe le fond derrière le verre comme une lentille sur le pourtour.
// (cf. kube.io/blog/liquid-glass-css-svg + nikdelvin/liquid-glass)
//
// En plus de la lentille statique :
//   1. Suivi du curseur (pointermove → position normalisée -0.5→0.5)
//   2. Élasticité : lerp (ressort) dans une boucle requestAnimationFrame
//   3. Spécularité dynamique : highlight radial repositionné selon le curseur (CSS ::after)
//   4. Intensification de la réfraction au survol (scale du displacement ↑)
//
// Cible : éléments portant la classe `.liquid` (chrome flottant L3). Délégation
// globale → fonctionne aussi sur les éléments rendus dynamiquement (dock, dropdown).

const REDUCED = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const EL = 0.16;            // élasticité du ressort (k du lerp)
const SCALE_REST = 18;     // force de réfraction au repos
const SCALE_HOVER = 30;    // force de réfraction au survol d'un .liquid

let active = null;          // élément .liquid survolé
let tx = 0, ty = 0;         // cible curseur (-0.5 → 0.5)
let cx = 0, cy = 0;         // valeurs courantes (lissées)
let tScale = SCALE_REST, cScale = SCALE_REST;

let disp = null;            // <feDisplacementMap id="lg-disp">
let rafId = null;

// ===== Displacement map « biseau arrondi » (générée une fois) =====
// SDF d'un rectangle arrondi : distance signée au bord (négative dehors).
function sdf(x, y, w, h, r) {
  const hx = w / 2, hy = h / 2;
  const px = Math.abs(x - hx) - (hx - r), py = Math.abs(y - hy) - (hy - r);
  return Math.hypot(Math.max(px, 0), Math.max(py, 0)) + Math.min(Math.max(px, py), 0) - r;
}

function makeMap(w, h, r, bezel) {
  const c = document.createElement('canvas'); c.width = w; c.height = h;
  const ctx = c.getContext('2d'), img = ctx.createImageData(w, h), d = img.data;
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    const i = (y * w + x) * 4;
    const dist = -sdf(x + 0.5, y + 0.5, w, h, r);     // > 0 à l'intérieur
    let t = 1 - dist / bezel; t = Math.max(0, Math.min(1, t));
    const s = t * t * (3 - 2 * t);                     // smoothstep : 1 au bord → 0 au centre
    // normale ≈ gradient de la SDF (différences finies)
    const nx = sdf(x + 1, y, w, h, r) - sdf(x - 1, y, w, h, r);
    const ny = sdf(x, y + 1, w, h, r) - sdf(x, y - 1, w, h, r);
    const nl = Math.hypot(nx, ny) || 1;
    d[i]     = 128 - (nx / nl) * s * 127;              // R = déplacement X
    d[i + 1] = 128 - (ny / nl) * s * 127;              // G = déplacement Y
    d[i + 2] = 128; d[i + 3] = 255;                    // B ignoré, A opaque
  }
  ctx.putImageData(img, 0, 0);
  return c.toDataURL();
}

function buildMap() {
  const m = document.getElementById('lg-map');
  if (!m) return;
  // Map générique étirée par feImage (preserveAspectRatio="none") sur chaque
  // élément : un rapport modéré + grand rayon donne un biseau crédible partout.
  const url = makeMap(240, 160, 46, 26);
  m.setAttribute('href', url);
  m.setAttribute('xlink:href', url); // compat anciens moteurs
}

// ===== Boucle réactive (tilt + spéculaire + intensité de réfraction) =====
function frame() {
  cx += (tx - cx) * EL;
  cy += (ty - cy) * EL;
  cScale += (tScale - cScale) * EL;

  if (disp) disp.setAttribute('scale', cScale.toFixed(1));

  if (active) {
    active.style.setProperty('--lg-rx', (-cy * 5).toFixed(2) + 'deg');
    active.style.setProperty('--lg-ry', (cx * 5).toFixed(2) + 'deg');
    active.style.setProperty('--lg-hx', (50 + cx * 90).toFixed(1) + '%');
    active.style.setProperty('--lg-hy', (50 + cy * 90).toFixed(1) + '%');
  }

  rafId = requestAnimationFrame(frame);
}

function onMove(e) {
  const el = e.target.closest && e.target.closest('.liquid');
  if (el !== active) {
    if (active) resetActive(active);
    active = el;
    tScale = el ? SCALE_HOVER : SCALE_REST;
  }
  if (!active) return;
  const r = active.getBoundingClientRect();
  tx = (e.clientX - r.left) / r.width - 0.5;
  ty = (e.clientY - r.top) / r.height - 0.5;
}

function resetActive(el) {
  el.style.setProperty('--lg-rx', '0deg');
  el.style.setProperty('--lg-ry', '0deg');
  el.style.setProperty('--lg-hx', '50%');
  el.style.setProperty('--lg-hy', '0%');
}

function onLeaveDoc() {
  if (active) resetActive(active);
  active = null;
  tx = ty = 0;
  tScale = SCALE_REST;
}

export function initLiquidGlass() {
  if (window.__lgReady) return;
  window.__lgReady = true;

  buildMap();                                   // construit la lentille (même en reduced-motion)
  disp = document.getElementById('lg-disp');

  if (REDUCED) return; // pas d'animation : la lentille reste statique (scale du HTML)

  document.addEventListener('pointermove', onMove, { passive: true });
  document.addEventListener('pointerleave', onLeaveDoc);
  // Pause/reprise quand l'onglet n'est pas visible (économie CPU/GPU)
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) { if (rafId) cancelAnimationFrame(rafId); rafId = null; }
    else if (!rafId) rafId = requestAnimationFrame(frame);
  });

  rafId = requestAnimationFrame(frame);
}
