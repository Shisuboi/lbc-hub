// js/lib/comment-seen.js
// Suivi "vu / pas vu" des commentaires par item, dans localStorage (pas de base — voir spec C-4).
// Map { [opportunityId]: dernierISOvu }. Tout accès est best-effort (mode privé / quota).
const KEY = 'lbc-comment-seen';

function readMap() {
  try { return JSON.parse(localStorage.getItem(KEY)) || {}; }
  catch (_) { return {}; }
}
function writeMap(m) {
  try { localStorage.setItem(KEY, JSON.stringify(m)); }
  catch (_) { /* localStorage indisponible : on dégrade en "pas de suivi" */ }
}

/** Mémorise `iso` comme dernier commentaire vu pour cet item (n'avance jamais en arrière). */
export function markSeen(opportunityId, iso) {
  if (!opportunityId || !iso) return;
  const m = readMap();
  if (!m[opportunityId] || iso > m[opportunityId]) {
    m[opportunityId] = iso;
    writeMap(m);
  }
}

/** true si `latestIso` est plus récent que le "vu" stocké (ou si rien n'a été vu mais qu'il y a du contenu). */
export function isUnseen(opportunityId, latestIso) {
  if (!latestIso) return false;
  const seen = readMap()[opportunityId];
  return !seen || latestIso > seen;
}
