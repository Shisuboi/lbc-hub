// js/pages/hub.js
// Page /hub : feed des recherches publiées par tous les users.
// Subscribe à Supabase Realtime pour afficher les nouvelles searches sans refresh.
// Toolbar de tri (date / score / prix) et filtres (plateforme, auteur, texte).
import { supa } from '../supabase-client.js';
import { requireAuth, getProfile } from '../auth.js';
import { feedCardHtml } from '../components/feed-card.js';
import { loadFavorites, toggleFavorite, isFavorite } from '../lib/favorites.js';

const PLATFORM_LABELS = {
    leboncoin: '🟠 LBC',
    ebay: '🔵 eBay',
    vinted: '🟢 Vinted',
    other: '⚪ Autre',
};

export async function render() {
    await requireAuth();

    const root = document.getElementById('appRoot');
    root.innerHTML = `
        <section class="hub-panel">
            <div class="hub-header">
                <h2>Hub des recherches</h2>
                <a href="/scraper" data-link class="btn btn-primary">🔍 Nouvelle recherche</a>
            </div>

            <div class="hub-toolbar card" id="hubToolbar">
                <div class="hub-toolbar-row">
                    <div class="hub-search">
                        <span class="search-icon">🔍</span>
                        <input type="text" id="hubFilterText" placeholder="Filtrer par titre ou pseudo...">
                    </div>
                    <div class="hub-filter-group">
                        <label for="hubSort">Trier :</label>
                        <select id="hubSort">
                            <option value="recent">Plus récentes ⏱️</option>
                            <option value="score">Meilleures notes ⭐</option>
                            <option value="price-asc">Prix croissant 📈</option>
                            <option value="price-desc">Prix décroissant 📉</option>
                        </select>
                    </div>
                </div>
                <div class="hub-toolbar-row">
                    <div class="hub-chip-row" id="hubPlatformChips">
                        <span class="hub-chip-label">Plateforme :</span>
                        <button type="button" class="hub-chip is-active" data-platform="all">Toutes</button>
                    </div>
                    <div class="hub-chip-row" id="hubAuthorChips">
                        <span class="hub-chip-label">Auteur :</span>
                        <button type="button" class="hub-chip is-active" data-author="all">Tous</button>
                    </div>
                    <div class="hub-chip-row" id="hubFavChips">
                        <button type="button" class="hub-chip hub-chip-fav" data-fav-filter="off" title="Filtrer sur mes favoris">☆ Favoris</button>
                        <button type="button" id="btnEnableNotif" class="hub-chip hub-chip-notif" title="Recevoir une notification quand quelqu'un publie">🔕 Activer notifications</button>
                    </div>
                </div>
                <div class="hub-toolbar-row hub-toolbar-counter">
                    <span id="hubResultCount" class="muted small">— recherches</span>
                </div>
            </div>

            <div id="feedGrid" class="feed-grid"></div>
            <div id="feedEmpty" class="empty-state card hidden">
                <h3>Pas encore de recherche publiée</h3>
                <p>Sois le premier à scraper et publier une recherche sur le hub !</p>
                <a href="/scraper" data-link class="btn btn-primary">Lancer une recherche</a>
            </div>
            <div id="feedNoMatch" class="empty-state card hidden">
                <h3>Aucune recherche ne correspond</h3>
                <p>Essaie de relâcher tes filtres.</p>
            </div>
        </section>
    `;

    // === State partagé entre fetch initial, filters, et Realtime ===
    const state = {
        searches: [],
        profileMap: new Map(),
        sort: 'recent',
        platform: 'all',
        author: 'all',
        favOnly: false,
        text: '',
    };

    // === Charge les favoris du user courant ===
    const me = await getProfile();
    await loadFavorites(me?.id);

    // === Fetch initial ===
    const { data: searches, error } = await supa
        .from('searches')
        .select('id, user_id, title, platform, model_name, model_type, listing_count, best_score, min_price, scraped_at, created_at')
        .order('created_at', { ascending: false })
        .limit(50);

    if (error) {
        document.getElementById('feedGrid').innerHTML =
            `<div class="error-panel card">Erreur de chargement : ${error.message}</div>`;
        return;
    }

    state.searches = searches || [];

    if (state.searches.length === 0) {
        document.getElementById('feedEmpty')?.classList.remove('hidden');
        document.getElementById('hubToolbar')?.classList.add('hidden');
    } else {
        const userIds = [...new Set(state.searches.map(s => s.user_id))];
        const { data: profiles } = await supa
            .from('profiles')
            .select('id, username, avatar_color')
            .in('id', userIds);
        state.profileMap = new Map((profiles || []).map(p => [p.id, p]));
        rebuildChips();
        renderFeed();
    }

    // === Filtres & tri : événements UI ===
    document.getElementById('hubFilterText').addEventListener('input', (e) => {
        state.text = e.target.value.trim().toLowerCase();
        renderFeed();
    });
    document.getElementById('hubSort').addEventListener('change', (e) => {
        state.sort = e.target.value;
        renderFeed();
    });
    document.getElementById('hubPlatformChips').addEventListener('click', (e) => {
        const btn = e.target.closest('button[data-platform]');
        if (!btn) return;
        state.platform = btn.dataset.platform;
        document.querySelectorAll('#hubPlatformChips .hub-chip').forEach(b => b.classList.toggle('is-active', b === btn));
        renderFeed();
    });
    document.getElementById('hubAuthorChips').addEventListener('click', (e) => {
        const btn = e.target.closest('button[data-author]');
        if (!btn) return;
        state.author = btn.dataset.author;
        document.querySelectorAll('#hubAuthorChips .hub-chip').forEach(b => b.classList.toggle('is-active', b === btn));
        renderFeed();
    });
    document.getElementById('hubFavChips').addEventListener('click', (e) => {
        const btn = e.target.closest('button[data-fav-filter]');
        if (!btn) return;
        state.favOnly = !state.favOnly;
        btn.classList.toggle('is-active', state.favOnly);
        btn.textContent = state.favOnly ? '⭐ Favoris' : '☆ Favoris';
        renderFeed();
    });

    // Délégation : toggle favori au clic sur un bouton .fav-btn dans la grille
    document.getElementById('feedGrid').addEventListener('click', async (e) => {
        const btn = e.target.closest('.fav-btn');
        if (!btn) return;
        e.preventDefault();
        e.stopPropagation();
        const searchId = btn.dataset.favId;
        if (!me?.id) return;
        btn.disabled = true;
        try {
            const nowFav = await toggleFavorite(me.id, searchId);
            btn.classList.toggle('is-fav', nowFav);
            btn.textContent = nowFav ? '⭐' : '☆';
            btn.title = nowFav ? 'Retirer des favoris' : 'Ajouter aux favoris';
            // Si le filtre "favoris seulement" est actif, re-render pour faire disparaître la carte
            if (state.favOnly && !nowFav) renderFeed();
        } catch (err) {
            console.error('toggleFavorite failed', err);
        } finally {
            btn.disabled = false;
        }
    });

    // === Realtime : insertion d'une nouvelle recherche ===
    if (window.__hubChannel) {
        try { await supa.removeChannel(window.__hubChannel); } catch (_) {}
        window.__hubChannel = null;
    }

    const channel = supa.channel('searches-feed')
        .on('postgres_changes',
            { event: 'INSERT', schema: 'public', table: 'searches' },
            async (payload) => {
                const newSearch = payload.new;
                // Récupère le profil de l'auteur si pas déjà connu
                if (!state.profileMap.has(newSearch.user_id)) {
                    const { data: profile } = await supa
                        .from('profiles')
                        .select('id, username, avatar_color')
                        .eq('id', newSearch.user_id)
                        .single();
                    if (profile) state.profileMap.set(profile.id, profile);
                }
                // Ajoute en tête du state
                state.searches.unshift(newSearch);
                // Affiche la toolbar si c'était la première recherche
                document.getElementById('feedEmpty')?.classList.add('hidden');
                document.getElementById('hubToolbar')?.classList.remove('hidden');
                rebuildChips();
                renderFeed({ flagNewId: newSearch.id });

                // Notifications : si l'onglet n'est pas focus OU pas celui en avant-plan,
                // bump le compteur dans le titre + push une notif système si autorisée.
                // On n'incrémente pas si la nouvelle recherche vient de l'utilisateur courant.
                if (newSearch.user_id !== me?.id) {
                    notifyNewSearch(newSearch, state.profileMap.get(newSearch.user_id));
                }
            })
        .subscribe();

    window.__hubChannel = channel;

    // === Notifications : titre + Notification API ===
    // La permission browser, une fois accordée, n'est pas révocable depuis JS.
    // On ajoute donc un toggle "soft" en localStorage qui mute l'app sans toucher la permission.
    const BASE_TITLE = 'LBC DealFinder Hub';
    const NOTIF_PREF_KEY = 'hub-notif-enabled';
    let unreadCount = 0;
    function isSoftEnabled() {
        // null = jamais set → par défaut ON quand la permission est granted, OFF sinon
        const v = localStorage.getItem(NOTIF_PREF_KEY);
        if (v === 'true') return true;
        if (v === 'false') return false;
        return ('Notification' in window) && Notification.permission === 'granted';
    }
    function setSoftEnabled(on) {
        localStorage.setItem(NOTIF_PREF_KEY, on ? 'true' : 'false');
    }
    function notifActive() {
        return ('Notification' in window) && Notification.permission === 'granted' && isSoftEnabled();
    }
    function updateTitle() {
        document.title = unreadCount > 0 ? `(${unreadCount}) ${BASE_TITLE}` : BASE_TITLE;
    }
    function resetUnread() {
        if (unreadCount > 0) {
            unreadCount = 0;
            updateTitle();
        }
    }
    function notifyNewSearch(search, profile) {
        if (!document.hidden && document.hasFocus()) return; // déjà sur la page : pas besoin
        if (!notifActive()) return; // toggle OFF ou permission absente → on ignore complètement
        unreadCount += 1;
        updateTitle();
        try {
            new Notification(`Nouvelle recherche sur le hub`, {
                body: `${profile ? '@' + profile.username : 'Quelqu\'un'} a publié "${search.title}"`,
                icon: '/lbc-hub/favicon.ico',
                tag: 'lbc-hub-' + search.id, // évite les duplicates si un user re-fire
            });
        } catch (_) { /* ignore : Safari fallback */ }
    }
    document.addEventListener('visibilitychange', resetUnread);
    window.addEventListener('focus', resetUnread);
    resetUnread();

    // Bouton toggle notifications (toolbar)
    const btnNotif = document.getElementById('btnEnableNotif');
    if (btnNotif) {
        function refreshNotifBtn() {
            const perm = 'Notification' in window ? Notification.permission : 'denied';
            const soft = isSoftEnabled();
            const active = perm === 'granted' && soft;
            btnNotif.classList.toggle('is-active', active);
            btnNotif.disabled = perm === 'denied';
            if (perm === 'denied') {
                btnNotif.textContent = '🔕 Notifications bloquées';
                btnNotif.title = 'Bloqué dans les paramètres du navigateur — autorise les notifications pour ce site.';
            } else if (perm === 'default') {
                btnNotif.textContent = '🔕 Activer notifications';
                btnNotif.title = 'Cliquer pour autoriser les notifications système.';
            } else if (active) {
                btnNotif.textContent = '🔔 Notifications ON';
                btnNotif.title = 'Cliquer pour couper les notifications.';
            } else {
                btnNotif.textContent = '🔕 Notifications OFF';
                btnNotif.title = 'Cliquer pour réactiver les notifications.';
            }
        }
        refreshNotifBtn();
        btnNotif.addEventListener('click', async () => {
            if (!('Notification' in window) || Notification.permission === 'denied') return;
            if (Notification.permission === 'default') {
                const result = await Notification.requestPermission();
                if (result === 'granted') setSoftEnabled(true);
            } else {
                // permission granted : toggle soft
                setSoftEnabled(!isSoftEnabled());
            }
            refreshNotifBtn();
        });
    }

    // === Helpers ===
    function rebuildChips() {
        const platBar = document.getElementById('hubPlatformChips');
        const authBar0 = document.getElementById('hubAuthorChips');
        if (!platBar || !authBar0) return; // navigated away — bail out
        // Platforms : conserve l'ordre LBC/eBay/Vinted/Other et ne montre que celles présentes
        const platforms = new Set(state.searches.map(s => s.platform || 'other'));
        const platOrder = ['leboncoin', 'ebay', 'vinted', 'other'].filter(p => platforms.has(p));
        const platHtml = ['<span class="hub-chip-label">Plateforme :</span>',
            `<button type="button" class="hub-chip ${state.platform === 'all' ? 'is-active' : ''}" data-platform="all">Toutes</button>`,
            ...platOrder.map(p =>
                `<button type="button" class="hub-chip ${state.platform === p ? 'is-active' : ''}" data-platform="${p}">${PLATFORM_LABELS[p] || p}</button>`
            )].join('');
        platBar.innerHTML = platHtml;

        // Authors : tri alphabétique par pseudo
        const authorIds = [...new Set(state.searches.map(s => s.user_id))];
        const authors = authorIds
            .map(id => state.profileMap.get(id))
            .filter(Boolean)
            .sort((a, b) => a.username.localeCompare(b.username));
        const authBar = document.getElementById('hubAuthorChips');
        const authHtml = ['<span class="hub-chip-label">Auteur :</span>',
            `<button type="button" class="hub-chip ${state.author === 'all' ? 'is-active' : ''}" data-author="all">Tous</button>`,
            ...authors.map(p =>
                `<button type="button" class="hub-chip ${state.author === p.id ? 'is-active' : ''}" data-author="${p.id}">@${p.username}</button>`
            )].join('');
        authBar.innerHTML = authHtml;
    }

    function filterAndSort() {
        let list = state.searches.slice();

        if (state.platform !== 'all') {
            list = list.filter(s => (s.platform || 'other') === state.platform);
        }
        if (state.author !== 'all') {
            list = list.filter(s => s.user_id === state.author);
        }
        if (state.favOnly) {
            list = list.filter(s => isFavorite(s.id));
        }
        if (state.text) {
            list = list.filter(s => {
                const profile = state.profileMap.get(s.user_id);
                const haystack = `${s.title || ''} @${profile?.username || ''}`.toLowerCase();
                return haystack.includes(state.text);
            });
        }

        switch (state.sort) {
            case 'score':
                list.sort((a, b) => (b.best_score || 0) - (a.best_score || 0));
                break;
            case 'price-asc':
                list.sort((a, b) => (a.min_price ?? Infinity) - (b.min_price ?? Infinity));
                break;
            case 'price-desc':
                list.sort((a, b) => (b.min_price ?? -Infinity) - (a.min_price ?? -Infinity));
                break;
            default: // recent
                list.sort((a, b) => new Date(b.scraped_at || b.created_at) - new Date(a.scraped_at || a.created_at));
        }
        return list;
    }

    function renderFeed({ flagNewId = null } = {}) {
        const list = filterAndSort();
        const grid = document.getElementById('feedGrid');
        const counter = document.getElementById('hubResultCount');
        const noMatch = document.getElementById('feedNoMatch');
        if (!grid || !counter || !noMatch) return; // navigated away — bail out

        if (list.length === 0) {
            grid.innerHTML = '';
            noMatch.classList.remove('hidden');
            counter.textContent = `0 / ${state.searches.length} recherche${state.searches.length > 1 ? 's' : ''}`;
            return;
        }
        noMatch.classList.add('hidden');

        grid.innerHTML = list.map(s => feedCardHtml(s, state.profileMap.get(s.user_id), { isFavorite: isFavorite(s.id) })).join('');

        if (flagNewId) {
            const newCard = grid.querySelector(`[data-search-id="${flagNewId}"]`);
            if (newCard) newCard.classList.add('feed-card-new');
        }

        counter.textContent = list.length === state.searches.length
            ? `${list.length} recherche${list.length > 1 ? 's' : ''}`
            : `${list.length} / ${state.searches.length} recherche${state.searches.length > 1 ? 's' : ''}`;
    }
}
