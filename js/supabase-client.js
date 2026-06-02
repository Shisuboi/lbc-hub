// js/supabase-client.js
// Singleton client Supabase.
// La clé anon est PUBLIQUE et safe à committer — elle est protégée par les RLS policies.
// Ne JAMAIS mettre la service_role / secret key ici.

const SUPABASE_URL = 'https://pfkuphmpzhdmfwaifywj.supabase.co';
const SUPABASE_ANON_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InBma3VwaG1wemhkbWZ3YWlmeXdqIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzk4MzkyNjIsImV4cCI6MjA5NTQxNTI2Mn0.fyiwITeQyyDAeei6gQ1Uk6pQt4w81wJnQ12w051oEvk';

if (!window.supabase) {
    throw new Error('Supabase SDK not loaded. Check the <script> tag in index.html.');
}

export const supa = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
    auth: {
        persistSession: true,
        autoRefreshToken: false,           // désactivé : déclenche un appel HTTP bloquant au boot sur certains navigateurs
        detectSessionInUrl: false,         // pas de magic link → désactiver évite un parse URL au boot
        storage: window.localStorage,
        // No-op lock : évite que getUser/getSession reste bloqué sur navigator.locks
        // si un onglet "zombie" a gardé un lock (problème reproduit sur Edge & Firefox).
        lock: async (_name, _timeout, fn) => await fn(),
    },
});

// ─── Cache de session ────────────────────────────────────────────────────────
// PIÈGE : supa.auth.getSession() peut NE JAMAIS résoudre par intermittence
// (bug SDK reproduit : page bloquée sur ⏳ à la navigation, F5 obligatoire).
// On appelait getSession() à CHAQUE navigation (requireAuth) → surface du hang.
// Fix : on garde la session en cache (alimentée au boot + par onAuthStateChange
// au login/logout/refresh) et on ne rappelle JAMAIS getSession() en navigation.
// Le seul appel restant (boot / force) est protégé par un timeout.
let _cachedSession = null;
let _sessionLoaded = false;

export function setCachedSession(session) {
    _cachedSession = session;
    _sessionLoaded = true;
}

export async function getCachedSession({ force = false } = {}) {
    if (_sessionLoaded && !force) return _cachedSession;   // ← navigation : zéro appel SDK
    try {
        const { data } = await Promise.race([
            supa.auth.getSession(),
            new Promise((_, reject) => setTimeout(() => reject(new Error('getSession timeout')), 2500)),
        ]);
        _cachedSession = data.session;
        _sessionLoaded = true;
    } catch (e) {
        // getSession a hang → on ne bloque pas : on garde la dernière session connue.
        console.warn('[auth] getSession a expiré, session en cache conservée :', e?.message);
    }
    return _cachedSession;
}

export async function currentUser() {
    const session = await getCachedSession();
    return session?.user || null;
}

export async function currentProfile() {
    const user = await currentUser();
    if (!user) return null;
    const { data, error } = await supa
        .from('profiles')
        .select('id, username, avatar_color, role')
        .eq('id', user.id)
        .single();
    if (error) {
        console.error('[supabase] profile fetch failed', error);
        return null;
    }
    return data;
}

export function onAuthChange(callback) {
    return supa.auth.onAuthStateChange((event, session) => {
        setCachedSession(session);   // garde le cache à jour (login / logout / refresh / INITIAL_SESSION)
        callback(event, session);
    });
}
