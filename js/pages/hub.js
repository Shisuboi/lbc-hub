// js/pages/hub.js
// Page /hub : feed chronologique des recherches publiées par tous les users.
// Subscribe à Supabase Realtime pour afficher les nouvelles searches sans refresh.
import { supa } from '../supabase-client.js';
import { requireAuth } from '../auth.js';
import { feedCardHtml } from '../components/feed-card.js';

export async function render() {
    console.log('[hub] render start');
    await requireAuth();
    console.log('[hub] requireAuth OK');

    const root = document.getElementById('appRoot');
    root.innerHTML = `
        <section class="hub-panel">
            <div class="hub-header">
                <h2>Hub des recherches</h2>
                <a href="/scraper" data-link class="btn btn-primary">🔍 Nouvelle recherche</a>
            </div>
            <div id="feedGrid" class="feed-grid"></div>
            <div id="feedEmpty" class="empty-state card hidden">
                <h3>Pas encore de recherche publiée</h3>
                <p>Sois le premier à scraper et publier une recherche sur le hub !</p>
                <a href="/scraper" data-link class="btn btn-primary">Lancer une recherche</a>
            </div>
            <p class="hub-disclaimer">💡 <em>Les notes d'un modèle cloud (Claude, GPT-4) sont généralement plus précises que celles d'un modèle local. Tenez-en compte en comparant des recherches entre elles.</em></p>
        </section>
    `;

    // === Fetch initial ===
    console.log('[hub] before fetch searches');
    const { data: searches, error } = await supa
        .from('searches')
        .select('id, user_id, title, platform, model_name, model_type, listing_count, best_score, min_price, scraped_at, created_at')
        .order('created_at', { ascending: false })
        .limit(50);
    console.log('[hub] fetch searches done, error =', error, 'count =', searches?.length);

    if (error) {
        document.getElementById('feedGrid').innerHTML =
            `<div class="error-panel card">Erreur de chargement : ${error.message}</div>`;
        return;
    }

    if (!searches || searches.length === 0) {
        document.getElementById('feedEmpty').classList.remove('hidden');
    } else {
        // Fetch tous les profils auteurs en un seul appel
        const userIds = [...new Set(searches.map(s => s.user_id))];
        const { data: profiles } = await supa
            .from('profiles')
            .select('id, username, avatar_color')
            .in('id', userIds);
        const profileMap = new Map((profiles || []).map(p => [p.id, p]));

        document.getElementById('feedGrid').innerHTML = searches
            .map(s => feedCardHtml(s, profileMap.get(s.user_id)))
            .join('');
    }

    // === Realtime : insertion d'une nouvelle recherche ===
    // On nettoie d'abord une éventuelle subscription d'une visite précédente,
    // car le router ne notifie pas la sortie de la page.
    if (window.__hubChannel) {
        try { await supa.removeChannel(window.__hubChannel); } catch (_) {}
        window.__hubChannel = null;
    }

    const channel = supa.channel('searches-feed')
        .on('postgres_changes',
            { event: 'INSERT', schema: 'public', table: 'searches' },
            async (payload) => {
                const newSearch = payload.new;
                const { data: profile } = await supa
                    .from('profiles')
                    .select('id, username, avatar_color')
                    .eq('id', newSearch.user_id)
                    .single();
                const grid = document.getElementById('feedGrid');
                if (!grid) return; // l'user a quitté la page
                const wrapper = document.createElement('div');
                wrapper.innerHTML = feedCardHtml(newSearch, profile);
                const card = wrapper.firstElementChild;
                if (card) {
                    card.classList.add('feed-card-new');
                    grid.insertBefore(card, grid.firstChild);
                }
                document.getElementById('feedEmpty')?.classList.add('hidden');
            })
        .subscribe();

    window.__hubChannel = channel;
}
