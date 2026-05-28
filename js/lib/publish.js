// js/lib/publish.js
// Publie une recherche + ses listings dans Supabase via le SDK JS.
// Le user doit être authentifié (RLS vérifie auth.uid()).
import { supa } from '../supabase-client.js';

/**
 * @param {Object} payload
 * @param {string} payload.title
 * @param {string} [payload.criteria]
 * @param {string|null} [payload.source_url]
 * @param {'leboncoin'|'ebay'|'vinted'|'other'} [payload.platform='leboncoin']
 * @param {string} payload.model_name
 * @param {'cloud'|'local'} payload.model_type
 * @param {Date|string|null} [payload.scraped_at]
 * @param {Array} payload.listings
 * @returns {Promise<string>} l'ID de la search créée
 */
export async function publishSearch(payload) {
    const { data: { session } } = await supa.auth.getSession();
    const user = session?.user;
    if (!user) throw new Error('Non authentifié. Reconnecte-toi.');

    const listings = payload.listings || [];

    // Calcul agrégats côté client
    const notes  = listings.map(l => parseFloat(l.note_sur_100)).filter(n => !Number.isNaN(n));
    const prices = listings.map(l => parseFloat(l.prix)).filter(p => !Number.isNaN(p) && p > 0);
    const best_score = notes.length  ? Math.max(...notes)  : null;
    const min_price  = prices.length ? Math.min(...prices) : null;

    // 1. Insert la search
    const scrapedAtIso = payload.scraped_at
        ? new Date(payload.scraped_at).toISOString()
        : new Date().toISOString();

    const { data: search, error: e1 } = await supa.from('searches').insert({
        user_id: user.id,
        title: payload.title,
        criteria: payload.criteria || '',
        source_url: payload.source_url || null,
        platform: payload.platform || 'leboncoin',
        model_name: payload.model_name,
        model_type: payload.model_type,
        listing_count: listings.length,
        best_score,
        min_price,
        scraped_at: scrapedAtIso,
    }).select().single();

    if (e1) throw new Error('Échec création recherche : ' + e1.message);

    // 2. Bulk insert des listings (chunks de 100 pour éviter limite body size)
    if (listings.length) {
        const rows = listings.map(l => ({
            search_id: search.id,
            titre: String(l.titre || '').slice(0, 1000),
            prix: parseFloat(l.prix) || null,
            url: l.url || null,
            note_sur_100: parseFloat(l.note_sur_100) || null,
            caracteristiques: l.caracteristiques || '',
            explication: l.explication || '',
            match_criteres: !!l.match_criteres,
        }));
        for (let i = 0; i < rows.length; i += 100) {
            const chunk = rows.slice(i, i + 100);
            const { error: e2 } = await supa.from('listings').insert(chunk);
            if (e2) {
                // Rollback : supprimer la search déjà créée pour éviter une coquille vide
                await supa.from('searches').delete().eq('id', search.id);
                throw new Error('Échec insertion annonces : ' + e2.message);
            }
        }
    }

    return search.id;
}

/**
 * Déduit le type de modèle (cloud vs local) à partir de son nom.
 * Utile quand on publie depuis le scraper où on a juste le nom du modèle.
 */
export function inferModelType(modelName) {
    const n = (modelName || '').toLowerCase();
    if (n.includes('claude') || n.includes('gpt') || n.includes('gemini')
        || n.includes('mistral-large') || n.includes('command-r')) {
        return 'cloud';
    }
    return 'local';
}
