// js/auth.js
// Helpers d'authentification + guard pour pages protégées.
import { supa, currentProfile } from './supabase-client.js';
import { navigate } from './router.js';

let cachedProfile = null;

export async function loginWithPassword(email, password) {
    const { data, error } = await supa.auth.signInWithPassword({ email, password });
    if (error) throw error;
    cachedProfile = await currentProfile();
    return data;
}

export async function logout() {
    await supa.auth.signOut();
    cachedProfile = null;
    navigate('/');
}

export async function getProfile(force = false) {
    if (!cachedProfile || force) cachedProfile = await currentProfile();
    return cachedProfile;
}

/**
 * Guard pour les pages authentifiées. À appeler en début de loader.
 *  - Pas connecté → redirige vers /
 *  - Connecté mais sans profil → redirige vers /onboarding
 * Lève une Error que le router intercepte pour stopper le rendu.
 */
export async function requireAuth({ requireProfile = true, requireRole = null } = {}) {
    const { data: { session } } = await supa.auth.getSession();
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
            navigate('/hub');
            throw new Error(`Insufficient role: needs ${requireRole}`);
        }
    }
}
