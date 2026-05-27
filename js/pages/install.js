// js/pages/install.js
// Guide d'installation public (accessible sans compte).
// Le lien de téléchargement Drive sera mis à jour à la Task 9.4 du plan.

const DRIVE_ZIP_URL = 'https://drive.google.com/REMPLACER_PAR_LIEN';

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
                        <h3>Installer Ollama (optionnel mais recommandé)</h3>
                        <p>Pour analyser les annonces avec une IA locale, télécharge <a href="https://ollama.com/download" target="_blank" rel="noopener">Ollama</a> puis dans un terminal :</p>
                        <p><code>ollama pull qwen2.5:0.5b</code> <em>(modèle léger pour commencer)</em></p>
                        <p class="muted small">Tu peux aussi utiliser <strong>Claude.ai / ChatGPT</strong> via l'export JSON, mais Ollama permet l'analyse 100% locale.</p>
                    </li>
                    <li>
                        <h3>Lancer le serveur</h3>
                        <p>Double-clic sur <code>server.py</code> ou dans un terminal : <code>python server.py</code>. <strong>Garde la fenêtre ouverte</strong> tant que tu scrapes.</p>
                    </li>
                    <li>
                        <h3>Se connecter au hub</h3>
                        <p>Reviens sur ce site et connecte-toi avec ton compte (créé via le lien d'invitation que tu as reçu). Ton scraper local est détecté automatiquement.</p>
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
