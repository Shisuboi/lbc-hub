// js/components/header.js
// Topbar : logo + nav + menu utilisateur. Re-render à chaque changement de session.
import { supa } from '../supabase-client.js';
import { getProfile, logout } from '../auth.js';

export async function renderHeader() {
    const el = document.getElementById('appHeader');
    if (!el) return;

    const { data: { session } } = await supa.auth.getSession();
    const user = session?.user;
    const profile = user ? await getProfile() : null;

    if (!user) {
        el.innerHTML = `
            <div class="logo-area">
                <span class="logo-icon">🤖</span>
                <div class="logo-text">
                    <h1>LBC DealFinder <span class="accent-text">Hub</span></h1>
                </div>
            </div>
            <nav class="header-nav">
                <a href="/install" data-link class="btn btn-ghost">Installation</a>
            </nav>
        `;
        return;
    }

    const currentPath = location.pathname.replace('/lbc-hub', '') || '/';
    function navLink(href, emoji, label) {
        const active = currentPath === href || currentPath.startsWith(href + '/');
        return `<a href="${href}" data-link class="nav-link${active ? ' is-active' : ''}">${emoji} ${label}</a>`;
    }

    const initial = (profile?.username || '?')[0].toUpperCase();
    const color = profile?.avatar_color || '#888';
    el.innerHTML = `
        <div class="logo-area">
            <a href="/hub" data-link class="logo-link">
                <span class="logo-icon">🤖</span>
                <div class="logo-text">
                    <h1>LBC DealFinder <span class="accent-text">Hub</span></h1>
                </div>
            </a>
        </div>
        <nav class="header-nav">
            ${navLink('/hub',       '🏠', 'Hub')}
            ${navLink('/dashboard', '📊', 'Dashboard')}
            ${navLink('/scraper',   '🔍', 'Scraper')}
            ${profile?.role === 'admin' ? navLink('/admin', '🛠️', 'Admin') : ''}
            <div class="user-menu" id="userMenu">
                <button class="user-menu-trigger" id="userMenuBtn" type="button">
                    <span class="user-avatar" style="background:${color}">${initial}</span>
                    <span class="user-name">@${profile?.username || '...'}</span>
                </button>
                <div class="user-menu-dropdown hidden" id="userDropdown">
                    <a href="/profile/${profile?.username || ''}" data-link>Mon profil</a>
                    <button id="btnLogout" type="button">Déconnexion</button>
                </div>
            </div>
        </nav>
    `;

    const btn = document.getElementById('userMenuBtn');
    const dropdown = document.getElementById('userDropdown');
    btn.addEventListener('click', (e) => {
        e.stopPropagation();
        dropdown.classList.toggle('hidden');
    });
    document.addEventListener('click', (e) => {
        if (!btn.contains(e.target) && !dropdown.contains(e.target)) {
            dropdown.classList.add('hidden');
        }
    });
    document.getElementById('btnLogout').addEventListener('click', logout);
}
