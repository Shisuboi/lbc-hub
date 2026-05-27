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
        autoRefreshToken: true,
        storage: window.localStorage,
    },
});

export async function currentUser() {
    const { data: { user } } = await supa.auth.getUser();
    return user;
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
