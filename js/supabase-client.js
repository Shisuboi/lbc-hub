// js/supabase-client.js
// Singleton client Supabase.
// La clé anon est PUBLIQUE et safe à committer — elle est protégée par les RLS policies.
// Ne JAMAIS mettre la service_role / secret key ici.

const SUPABASE_URL = 'https://pfkuphmpzhdmfwaifywj.supabase.co';
const SUPABASE_ANON_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InBma3VwaG1wemhkbWZ3YWlmeXdqIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzk4MzkyNjIsImV4cCI6MjA5NTQxNTI2Mn0.fyiwITeQyyDAeei6gQ1Uk6pQt4w81wJnQ12w051oEvk';

if (!window.supabase) {
    throw new Error('Supabase SDK not loaded. Check the <script> tag in index.html.');
}

console.log('[supa-client] before createClient');
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
console.log('[supa-client] after createClient');

export async function currentUser() {
    // getSession() lit localStorage sans appel réseau (≠ getUser() qui valide côté serveur).
    // Suffisant pour les guards d'auth ; les requêtes DB échoueront proprement si le token est invalide.
    const { data: { session } } = await supa.auth.getSession();
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
    return supa.auth.onAuthStateChange((event, session) => callback(event, session));
}
