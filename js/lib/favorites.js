// js/lib/favorites.js
// Helpers pour gérer les favoris d'un user (table public.favorites).
// Charge la liste en mémoire au boot de la page (cheap : 1 query) puis
// mute localement à chaque toggle pour réactivité immédiate.

import { supa } from '../supabase-client.js';

let cache = null; // Set<search_id>
let cacheUserId = null;

export async function loadFavorites(userId) {
    if (!userId) { cache = new Set(); cacheUserId = null; return cache; }
    if (cache && cacheUserId === userId) return cache;
    const { data, error } = await supa
        .from('favorites')
        .select('search_id')
        .eq('user_id', userId);
    if (error) {
        console.error('[favorites] load failed', error);
        cache = new Set();
    } else {
        cache = new Set((data || []).map(r => r.search_id));
    }
    cacheUserId = userId;
    return cache;
}

export function isFavorite(searchId) {
    return cache?.has(searchId) || false;
}

export async function toggleFavorite(userId, searchId) {
    if (!cache) await loadFavorites(userId);
    const wasFav = cache.has(searchId);
    if (wasFav) {
        cache.delete(searchId);
        const { error } = await supa
            .from('favorites')
            .delete()
            .eq('user_id', userId)
            .eq('search_id', searchId);
        if (error) { cache.add(searchId); throw error; } // rollback
    } else {
        cache.add(searchId);
        const { error } = await supa
            .from('favorites')
            .insert({ user_id: userId, search_id: searchId });
        if (error) { cache.delete(searchId); throw error; }
    }
    return !wasFav; // nouvelle valeur
}

export function getFavorites() {
    return cache || new Set();
}
