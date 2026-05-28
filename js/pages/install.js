// js/pages/install.js
// Guide d'installation public (accessible sans compte).
// Le lien de téléchargement Drive sera mis à jour à la Task 9.4 du plan.

// URL de téléchargement direct (uc?export=download&id=...) — bypasse la preview Drive
// pour déclencher le download immédiatement au clic.
const DRIVE_ZIP_URL = 'https://drive.google.com/uc?export=download&id=1RepbQqKB_eqB5eRd3ooWmQOSnr7RsyCR';

export async function render() {
    document.getElementById('appRoot').innerHTML = `
        <section class="install-page">
            <div class="install-card card">
                <h1>📦 Installation de LBC DealFinder Hub</h1>
                <p class="lead">Pour scraper Leboncoin, tu dois lancer un petit serveur Python sur ton ordi (le scraping ne marche pas depuis le cloud — Leboncoin bloque les serveurs distants). Une fois le serveur lancé, tout le reste fonctionne depuis ce site.</p>

                <ol class="install-steps">
                    <li>
                        <h3>Télécharger Python 3.11+</h3>
                        <p>Si tu n'as pas Python : <a href="https://www.python.org/downloads/" target="_blank" rel="noopener">python.org/downloads</a> (coche bien <strong>"Add Python to PATH"</strong> pendant l'install).</p>
                    </li>
                    <li>
                        <h3>Télécharger l'application</h3>
                        <p><a href="${DRIVE_ZIP_URL}" target="_blank" rel="noopener" class="btn btn-primary">📥 Télécharger lbc-dealfinder.zip</a></p>
                        <p class="muted small">Le lien Drive est tenu à jour par l'admin. Si le lien est cassé, demande-lui directement.</p>
                    </li>
                    <li>
                        <h3>Décompresser et installer</h3>
                        <p>Double-clic sur <code>install.bat</code> (Windows) ou exécute <code>./install.sh</code> (Mac/Linux). Ça installe Playwright + aiohttp et télécharge un Chromium léger pour le scraping.</p>
                    </li>
                    <li>
                        <h3>Lancer le serveur</h3>
                        <p>Écrit dans un terminal : <code>python server.py</code>. <strong>Garde la fenêtre ouverte</strong> tant que tu scrapes.</p>
                    </li>
                    <li>
                        <h3>Se connecter au hub</h3>
                        <p>Reviens sur ce site et connecte-toi avec ton compte (créé via le lien d'invitation que tu as reçu). Ton scraper local est détecté automatiquement.</p>
                        <p class="muted small">L'analyse des annonces se fait via <strong>Claude.ai</strong> : depuis la page Scraper, clique sur <em>"📋 Générer le Prompt pour Claude.ai"</em>, colle-le dans une conversation Claude, puis importe le JSON renvoyé.</p>
                    </li>
                </ol>

                <div class="install-warning card">
                    <h3>⚠️ Note pour Firefox / Safari</h3>
                    <p>Chrome et Edge fonctionnent directement (ils autorisent les appels HTTPS → http://localhost). Sur Firefox et Safari, le navigateur bloque ces appels (mixed content). <strong>Utilise Chrome ou Edge pour le scraper.</strong> Tu peux toujours consulter le hub depuis n'importe quel navigateur.</p>
                </div>

                <p class="install-footer"><a href="/" data-link>← Retour à la connexion</a></p>
            </div>
        </section>
    `;
}
