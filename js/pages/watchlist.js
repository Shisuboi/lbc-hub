// js/pages/watchlist.js
// Placeholder C-1 : la vraie page de gestion des recherches surveillées arrive en C-3
// (ajout/édition par tous les membres, une seule active à la fois via RPC).
import { requireAuth } from '../auth.js';
import { navState } from '../router.js';

export async function render() {
  const myToken = navState.token;
  await requireAuth();
  if (navState.token !== myToken) return;

  document.getElementById('appRoot').innerHTML = `
    <section class="feed-page">
      <h2>📡 Recherches surveillées</h2>
      <p class="muted">Ce que le PC scrape en continu.</p>
      <div class="card" style="padding:22px;text-align:center;color:var(--c-mut)">
        🛠️ Cette page arrive bientôt (sous-phase C-3).<br>
        On pourra y ajouter des recherches Leboncoin et choisir laquelle tourne (une seule active à la fois).
      </div>
    </section>`;
}
