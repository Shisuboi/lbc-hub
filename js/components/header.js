// js/components/header.js
// Chrome global type « app de streaming » :
//   - RAIL gauche (fixe) : logo, Favoris, et le COMPTE (avatar → profil / déconnexion)
//   - DOCK bas (fixe, centré) : navigation principale en PICTOGRAMMES (pas d'emoji)
// Re-render à chaque changement de session.
import { getCachedSession } from '../supabase-client.js';
import { getProfile, logout } from '../auth.js';
import { icon } from '../lib/icons.js';

// Resynchronise l'état actif du chrome (rail + dock) à CHAQUE navigation SPA.
// (Le header n'est re-rendu qu'au changement de session ; sans ça le point « page
//  active » du dock resterait figé sur la page de premier rendu.)
function curPath() { return location.pathname.replace('/lbc-hub', '') || '/'; }
function pathActive(href, p) { return href && (p === href || p.startsWith(href + '/')); }
function updateActiveNav() {
  const p = curPath();
  document.querySelectorAll('.dock-item, .rail-item').forEach(a => {
    const href = (a.getAttribute('href') || '').split('#')[0];
    a.classList.toggle('is-active', pathActive(href, p));
  });
}
window.addEventListener('spa:navigated', updateActiveNav);

export async function renderHeader() {
  const el = document.getElementById('appHeader');
  if (!el) return;

  const session = await getCachedSession();
  const user = session?.user;
  const profile = user ? await getProfile() : null;

  if (!user) {
    // Déconnecté : marque seule, pas de rail/dock (page de login épurée).
    el.innerHTML = `
      <div class="chrome-signedout">
        <span class="brand"><span class="brand-glyph">${icon('bolt', { size: 18 })}</span>
          <span class="brand-name">LBC<span class="accent-text">Hub</span></span></span>
        <a href="/install" data-link class="pill liquid">Installation</a>
      </div>`;
    return;
  }

  const currentPath = location.pathname.replace('/lbc-hub', '') || '/';
  const isActive = (href) => currentPath === href || currentPath.startsWith(href + '/');

  // Navigation principale (dock bas) — pictogrammes
  const dockItems = [
    { href: '/feed',      ic: 'home',    label: 'Accueil' },
    { href: '/watchlist', ic: 'radar',   label: 'Suivis' },
    { href: '/dashboard', ic: 'book',    label: 'Journal' },
  ];
  if (profile?.role === 'admin') dockItems.push({ href: '/admin', ic: 'sliders', label: 'Admin' });

  const dockHtml = dockItems.map(it => `
    <a href="${it.href}" data-link class="dock-item${isActive(it.href) ? ' is-active' : ''}" title="${it.label}" aria-label="${it.label}">
      ${icon(it.ic, { size: 24 })}<span class="dock-label">${it.label}</span>
    </a>`).join('');

  const initial = (profile?.username || '?')[0].toUpperCase();
  const color = profile?.avatar_color || '#888';

  el.innerHTML = `
    <aside class="rail" aria-label="Compte et favoris">
      <a href="/feed" data-link class="rail-logo" title="LBC Hub">${icon('bolt', { size: 20 })}</a>
      <div class="rail-nav">
        <a href="/favorites" data-link class="rail-item${isActive('/favorites') ? ' is-active' : ''}" title="Favoris" aria-label="Favoris">
          ${icon('heart', { size: 22 })}<span class="rail-label">Favoris</span>
        </a>
      </div>
      <div class="rail-account user-menu" id="userMenu">
        <button class="rail-avatar" id="userMenuBtn" type="button" aria-label="Compte">
          <span class="user-avatar" style="background:${color}">${initial}</span>
        </button>
        <div class="user-menu-dropdown liquid hidden" id="userDropdown">
          <div class="menu-handle">@${profile?.username || '...'}</div>
          <a href="/profile/${profile?.username || ''}" data-link>${icon('user', { size: 16 })} Mon profil</a>
          <button id="btnLogout" type="button">${icon('logout', { size: 16 })} Déconnexion</button>
        </div>
      </div>
    </aside>

    <nav class="dock liquid" aria-label="Navigation principale">
      ${dockHtml}
    </nav>`;

  const btn = document.getElementById('userMenuBtn');
  const dropdown = document.getElementById('userDropdown');
  btn.addEventListener('click', (e) => { e.stopPropagation(); dropdown.classList.toggle('hidden'); });
  document.addEventListener('click', (e) => {
    if (!btn.contains(e.target) && !dropdown.contains(e.target)) dropdown.classList.add('hidden');
  });
  document.getElementById('btnLogout').addEventListener('click', logout);
}
