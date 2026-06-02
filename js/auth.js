// js/auth.js
// Helpers d'authentification + guard pour pages protégées.
import { supa, currentProfile, getCachedSession, setCachedSession } from './supabase-client.js';
import { navigate, navTrace } from './router.js';

let cachedProfile = null;

export async function loginWithPassword(email, password) {
    const { data, error } = await supa.auth.signInWithPassword({ email, password });
    if (error) throw error;
    setCachedSession(data.session);   // alimente le cache de session dès le login
    cachedProfile = await currentProfile();
    return data;
}

export async function logout() {
    // Le SDK Supabase peut hang sur Firefox (POST /auth/v1/logout) ET peut garder
    // la session en mémoire même après un scope:'local'. On utilise une approche
    // bulletproof : best-effort SDK avec timeout, clear manuel du localStorage,
    // puis full reload pour purger toute state SDK en mémoire.
    cachedProfile = null;
    try {
        await Promise.race([
            supa.auth.signOut({ scope: 'local' }),
            new Promise(resolve => setTimeout(resolve, 600)),
        ]);
    } catch (_) { /* peu importe, on clear manuellement ensuite */ }
    // Clear sync des clés Supabase en storage (au cas où le SDK n'a rien fait)
    try {
        Object.keys(localStorage).forEach(k => {
            if (k.startsWith('sb-')) localStorage.removeItem(k);
        });
    } catch (_) { /* localStorage peut throw en mode privé */ }
    // Full reload vers la racine de l'app : purge tout in-memory + rend login
    const base = location.pathname.startsWith('/lbc-hub') ? '/lbc-hub/' : '/';
    location.href = base;
}

export async function getProfile(force = false) {
    const cacheHit = !!cachedProfile && !force;
    navTrace(`getProfile(force=${force}) → ${cacheHit ? 'CACHE' : 'FETCH réseau…'}`);
    if (!cachedProfile || force) cachedProfile = await currentProfile();
    navTrace(`getProfile résolu (profil=${cachedProfile ? 'ok' : 'null'})`);
    return cachedProfile;
}

/**
 * Guard pour les pages authentifiées. À appeler en début de loader.
 *  - Pas connecté → redirige vers /
 *  - Connecté mais sans profil → redirige vers /onboarding
 * Lève une Error que le router intercepte pour stopper le rendu.
 */
export async function requireAuth({ requireProfile = true, requireRole = null } = {}) {
    navTrace('requireAuth → getCachedSession()…');
    const session = await getCachedSession();   // cache : ne hang plus en navigation
    navTrace(`requireAuth session résolue (user=${session?.user ? 'ok' : 'aucun'})`);
    const user = session?.user;
    if (!user) {
        navigate('/');
        throw new Error('Not authenticated');
    }
    if (requireProfile) {
        // Pas de force=true : le cache est invalidé au login/logout, donc safe.
        // Forcer un fetch HTTP à chaque navigation causait un hang intermittent sur Firefox
        // (spinner ⏳ Chargement… figé) — voir CLAUDE.md "Bugs / pièges connus".
        const profile = await getProfile();
        if (!profile) {
            navigate('/onboarding');
            throw new Error('Profile not yet created');
        }
        if (requireRole && profile.role !== requireRole) {
            navigate('/feed');
            throw new Error(`Insufficient role: needs ${requireRole}`);
        }
    }
}
