// js/lib/server-ping.js
// Détection du server.py local. Utilisé par /scraper pour afficher un banner
// si l'utilisateur n'a pas lancé son serveur Python.
// Note : server.py renvoie Access-Control-Allow-Private-Network: true pour
// que le fetch fonctionne même depuis https://shisuboi.github.io.

export const LOCAL_SERVER_URL = 'http://localhost:8080';

export async function checkLocalServer() {
    try {
        const resp = await fetch(`${LOCAL_SERVER_URL}/api/ping`, {
            method: 'GET',
            mode: 'cors',
            cache: 'no-store',
        });
        if (!resp.ok) return false;
        const data = await resp.json();
        return data.status === 'ok';
    } catch (_) {
        return false;
    }
}
