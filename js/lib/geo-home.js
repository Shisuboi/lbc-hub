// js/lib/geo-home.js
// Domicile du membre + rayon, en localStorage (pas de DB). Géocodage via l'API BAN gratuite.
const KEY_HOME = 'lbc-home';      // { label, lat, lon }
const KEY_RADIUS = 'lbc-radius';  // '5' | '10' | '25' | '50' | '100' | 'all'
const BAN_URL = 'https://api-adresse.data.gouv.fr/search/';

/** Domicile mémorisé { label, lat, lon } ou null. */
export function getHome() {
  try { return JSON.parse(localStorage.getItem(KEY_HOME)) || null; }
  catch (_) { return null; }
}

export function clearHome() {
  try { localStorage.removeItem(KEY_HOME); } catch (_) {}
}

/** Géocode un code postal/ville via la BAN, mémorise et renvoie { label, lat, lon }. */
export async function setHome(query) {
  const q = (query || '').trim();
  if (!q) throw new Error('Indique un code postal ou une ville.');
  const resp = await fetch(`${BAN_URL}?q=${encodeURIComponent(q)}&limit=1`);
  if (!resp.ok) throw new Error('Géocodage indisponible, réessaie.');
  const data = await resp.json();
  const feat = (data.features || [])[0];
  if (!feat) throw new Error('Lieu introuvable.');
  const [lon, lat] = feat.geometry.coordinates;  // GeoJSON = [lon, lat]
  const home = { label: feat.properties.label, lat, lon };
  try { localStorage.setItem(KEY_HOME, JSON.stringify(home)); } catch (_) {}
  return home;
}

/** Rayon choisi ('all' par défaut). */
export function getRadius() {
  try { return localStorage.getItem(KEY_RADIUS) || 'all'; }
  catch (_) { return 'all'; }
}
export function setRadius(value) {
  try { localStorage.setItem(KEY_RADIUS, String(value)); } catch (_) {}
}

/** Distance en km entre deux points (Haversine). */
export function haversineKm(lat1, lon1, lat2, lon2) {
  const R = 6371, toRad = d => d * Math.PI / 180;
  const dLat = toRad(lat2 - lat1), dLon = toRad(lon2 - lon1);
  const a = Math.sin(dLat / 2) ** 2
    + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}
