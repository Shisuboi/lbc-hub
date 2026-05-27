// js/pages/scraper.js
// Encapsule l'outil scraper d'origine en tant que page SPA.
// La logique métier (fetch /api/start, EventSource SSE, modale prompt, import JSON)
// est migrée depuis l'ancien app.js. Tous les fetch vers l'API locale utilisent
// LOCAL_SERVER_URL (absolu) pour que ça fonctionne même quand le SPA est servi
// depuis https://shisuboi.github.io/lbc-hub.
import { requireAuth, getProfile } from '../auth.js';
import { checkLocalServer, LOCAL_SERVER_URL } from '../lib/server-ping.js';
import { publishSearch, inferModelType } from '../lib/publish.js';

const API = LOCAL_SERVER_URL;

// =========================================================================
// MARKUP (repris quasi à l'identique de index.html.scraper-backup,
// sans le <header> et le <div class="app-container"> qui sont gérés par le shell SPA)
// =========================================================================
function scraperMarkup() {
    return `
    <div class="scraper-status-row">
        <div class="status-indicator">
            <span class="status-dot status-idle" id="statusDot"></span>
            <span class="status-label" id="statusLabel">Serveur Prêt</span>
        </div>
    </div>

    <div class="scraper-grid">
        <!-- SIDEBAR CONFIGURATION -->
        <aside class="sidebar card">
            <h2 class="section-title">Configuration</h2>
            <form id="configForm">
                <div class="form-group">
                    <label for="urlInput">URL de Recherche Leboncoin</label>
                    <input type="url" id="urlInput" placeholder="https://www.leboncoin.fr/recherche?..." required autocomplete="off">
                    <small class="help-text">Copiez l'URL de recherche exacte depuis votre navigateur.</small>
                </div>

                <div class="form-row">
                    <div class="form-group">
                        <label for="pagesInput">Pages Max</label>
                        <input type="number" id="pagesInput" min="1" max="50" value="1" required>
                    </div>
                    <div class="form-group">
                        <label for="delayInput">Délai Scraping (ms)</label>
                        <input type="number" id="delayInput" min="0" max="10000" step="100" value="1500" required>
                    </div>
                </div>

                <div class="form-group">
                    <label for="criteresInput">Critères de recherche</label>
                    <textarea id="criteresInput" rows="4" placeholder="Ex: Ordinateur portable avec au moins 16 Go de RAM, processeur i7 récent ou Ryzen 7, carte graphique dédiée RTX..." required></textarea>
                    <small class="help-text">Ces critères seront utilisés par Claude.ai pour analyser les annonces et calculer le rapport qualité/prix.</small>
                </div>

                <div class="actions-area">
                    <button type="submit" id="btnStart" class="btn btn-primary">
                        <span class="btn-icon">⚡</span> Lancer le scraping
                    </button>
                    <button type="button" id="btnStop" class="btn btn-danger" disabled>
                        <span class="btn-icon">🛑</span> Arrêter
                    </button>

                    <!-- Étape post-scrape : invite à utiliser Claude.ai puis importer le JSON -->
                    <div id="claudeStepArea" class="claude-step hidden">
                        <h3>🤖 Étape suivante : analyser via Claude.ai</h3>
                        <ol class="claude-steps">
                            <li>Clique <strong>Copier le prompt</strong> ci-dessous</li>
                            <li>Ouvre <a href="https://claude.ai" target="_blank" rel="noopener">claude.ai</a>, colle le prompt</li>
                            <li>Joins le fichier <code>leboncoin_brut.json</code> (<a href="#" id="downloadRawLink">télécharger</a>)</li>
                            <li>Récupère le JSON renvoyé par Claude</li>
                            <li>Clique <strong>Importer le JSON</strong> ci-dessous</li>
                        </ol>
                        <button type="button" id="btnShowPrompt" class="btn btn-primary">
                            <span class="btn-icon">📋</span> Copier le prompt pour Claude.ai
                        </button>
                        <input type="file" id="importJsonFile" accept=".json" style="display:none">
                        <button type="button" id="btnImportResults" class="btn btn-secondary">
                            <span class="btn-icon">📥</span> Importer le JSON Claude.ai
                        </button>
                    </div>

                    <!-- Panneau de publication : reste dans la sidebar de config (proche des actions)
                         pour être visible sans devoir scroller dans la grille de résultats. -->
                    <div id="publishArea" class="publish-area hidden">
                        <h3>📤 Publier ces résultats sur le hub</h3>
                        <p class="muted">Ta recherche apparaîtra sur le feed pour tous les membres du groupe.</p>
                        <input type="text" id="publishTitle" placeholder="Titre de la recherche (ex: Laptops gaming RTX 4060)" maxlength="120">
                        <button id="btnPublish" class="btn btn-primary">📤 Publier sur le hub</button>
                        <div id="publishStatus" class="publish-status"></div>
                    </div>
                </div>
            </form>
        </aside>

        <!-- MAIN CONTENT AREA -->
        <main class="main-content">
            <div class="captcha-banner card hidden" id="captchaBanner">
                <div class="captcha-icon">⚠️</div>
                <div class="captcha-info">
                    <h3>Blocage anti-bot (Datadome) détecté !</h3>
                    <p>Une vérification humaine (Captcha) est apparue dans la fenêtre Chromium ouverte sur votre écran.</p>
                    <p class="instruction">Résolvez le Captcha là-bas, puis cliquez sur le bouton ci-contre pour reprendre.</p>
                </div>
                <button id="btnResume" class="btn btn-warning">🔓 J'ai résolu le Captcha</button>
            </div>

            <section class="view-panel" id="welcomeView">
                <div class="welcome-card card">
                    <div class="welcome-hero">🔍🤖💸</div>
                    <h2>Bienvenue sur Leboncoin DealFinder AI</h2>
                    <p>Cet outil utilise <strong>Playwright</strong> pour extraire les annonces de recherche Leboncoin, puis tu fais analyser leur description par <strong>Claude.ai</strong> (workflow copier-coller du prompt) pour dénicher les meilleures affaires du marché.</p>
                    <div class="steps-guide">
                        <div class="guide-step">
                            <div class="step-num">1</div>
                            <h4>Recherchez sur LBC</h4>
                            <p>Faites votre recherche sur le site Leboncoin et copiez l'adresse URL du résultat.</p>
                        </div>
                        <div class="guide-step">
                            <div class="step-num">2</div>
                            <h4>Précisez vos critères</h4>
                            <p>Décrivez ce que vous voulez (RAM, état, modèle exact). Claude.ai s'en servira pour noter les annonces.</p>
                        </div>
                        <div class="guide-step">
                            <div class="step-num">3</div>
                            <h4>Lancez le scraping</h4>
                            <p>Le serveur récupère les annonces, puis vous les passez à Claude.ai via le prompt fourni, et vous importez le JSON renvoyé.</p>
                        </div>
                    </div>
                </div>
            </section>

            <section class="view-panel hidden" id="progressView">
                <div class="progress-card card">
                    <div class="progress-header">
                        <h3 class="panel-subtitle">Progression en temps réel</h3>
                        <div class="pulse-indicator">
                            <span class="pulse-dot"></span>
                            <span id="progressStateText">Initialisation du navigateur...</span>
                        </div>
                    </div>
                    <div class="progress-bar-container">
                        <div class="progress-bar" id="progressBar"></div>
                    </div>
                    <div class="live-tabs" role="tablist">
                        <button type="button" class="live-tab active" id="tabBtnConsole" data-tab="console">🖥️ Console</button>
                        <button type="button" class="live-tab" id="tabBtnLive" data-tab="live">
                            ⭐ Notations en direct <span class="live-count" id="liveCount">0</span>
                        </button>
                    </div>
                    <div class="live-tab-panel" id="consolePanel">
                        <div class="console-wrapper">
                            <div class="console-header">
                                <span class="console-dot red"></span>
                                <span class="console-dot yellow"></span>
                                <span class="console-dot green"></span>
                                <span class="console-title">Console de sortie</span>
                                <button id="btnClearConsole" class="console-btn">Vider</button>
                            </div>
                            <div class="console-body" id="consoleLogs">
                                <div class="log-line log-system">> Prêt à démarrer le scraping...</div>
                            </div>
                        </div>
                    </div>
                    <div class="live-tab-panel hidden" id="livePanel">
                        <div class="live-grid-scroll">
                            <div class="grid-container" id="liveResultsGrid"></div>
                            <div class="live-empty" id="liveEmpty">⏳ En attente des premières notations de l'IA…</div>
                        </div>
                    </div>
                </div>
            </section>

            <section class="view-panel hidden" id="resultsView">
                <div class="results-toolbar card">
                    <div class="stats-overview">
                        <div class="stat-item">
                            <span class="stat-value" id="statTotalCount">0</span>
                            <span class="stat-label">Annonces retenues</span>
                        </div>
                        <div class="stat-item">
                            <span class="stat-value text-gold" id="statBestScore">0/100</span>
                            <span class="stat-label">Meilleure Note</span>
                        </div>
                        <div class="stat-item">
                            <span class="stat-value text-emerald" id="statMinPrice">0 €</span>
                            <span class="stat-label">Prix minimum</span>
                        </div>
                    </div>
                    <div class="filter-controls">
                        <div class="search-box">
                            <span class="search-icon">🔍</span>
                            <input type="text" id="filterSearch" placeholder="Filtrer par titre, spec...">
                        </div>
                        <div class="filter-group">
                            <label for="filterMinScore">Note min :</label>
                            <select id="filterMinScore">
                                <option value="0">Toutes</option>
                                <option value="40">>= 40/100</option>
                                <option value="60">>= 60/100 (Correctes)</option>
                                <option value="75">>= 75/100 (Bonnes affaires)</option>
                                <option value="85">>= 85/100 (Super affaires)</option>
                            </select>
                        </div>
                        <div class="filter-group">
                            <label for="sortSelector">Trier :</label>
                            <select id="sortSelector">
                                <option value="note-desc">Meilleures Notes ⭐</option>
                                <option value="price-asc">Prix croissant 📈</option>
                                <option value="price-desc">Prix décroissant 📉</option>
                            </select>
                        </div>
                    </div>
                </div>
                <div class="grid-container" id="resultsGrid"></div>
                <div id="noResultsAlert" class="card empty-state hidden">
                    <div class="empty-icon">📂</div>
                    <h3>Aucune annonce correspondante</h3>
                    <p>Essayez de modifier vos filtres de recherche ou de changer les critères IA.</p>
                </div>

            </section>
        </main>
    </div>

    <!-- MODALE : PROMPT POUR IA EN LIGNE -->
    <div id="promptModal" class="modal-overlay hidden">
        <div class="modal-card card">
            <div class="modal-header">
                <div class="modal-title-area">
                    <span class="modal-icon">🤖</span>
                    <h2>Utiliser une IA en ligne (Claude.ai, Gemini…)</h2>
                </div>
                <button id="btnCloseModal" class="modal-close" title="Fermer">✕</button>
            </div>
            <div class="modal-body">
                <div class="modal-steps">
                    <div class="modal-step">
                        <span class="step-badge">1</span>
                        <div class="step-content">
                            <strong>Scrapez d'abord les annonces</strong> avec le bouton <em>⚡ Lancer le scraping</em>. Une fois terminé, le fichier <code>leboncoin_brut.json</code> est créé dans le dossier de l'application.
                        </div>
                    </div>
                    <div class="modal-step">
                        <span class="step-badge">2</span>
                        <div class="step-content">
                            <strong>Ouvrez</strong> <a href="https://claude.ai" target="_blank" rel="noopener">Claude.ai</a>, Gemini, ChatGPT ou toute IA en ligne.<br>
                            Créez un nouveau message et <strong>attachez le fichier</strong> <code>leboncoin_brut.json</code>.
                        </div>
                    </div>
                    <div class="modal-step">
                        <span class="step-badge">3</span>
                        <div class="step-content">
                            <strong>Copiez le prompt ci-dessous</strong> (il inclut déjà vos critères) et collez-le dans votre message IA, puis envoyez.
                        </div>
                    </div>
                </div>
                <div class="prompt-box">
                    <div class="prompt-box-header">
                        <span class="prompt-box-label">Prompt généré (basé sur vos critères)</span>
                        <button id="btnCopyPrompt" class="btn-copy-prompt">
                            <span id="copyPromptIcon">📋</span><span id="copyPromptText"> Copier le prompt</span>
                        </button>
                    </div>
                    <textarea id="generatedPrompt" class="prompt-textarea" readonly spellcheck="false"></textarea>
                </div>
                <div class="modal-steps" style="margin-top:0">
                    <div class="modal-step">
                        <span class="step-badge">4</span>
                        <div class="step-content">
                            L'IA va vous retourner un bloc JSON. <strong>Copiez-le dans un fichier texte, renommez-le en <code>.json</code></strong> et sauvegardez-le sur votre disque.
                        </div>
                    </div>
                    <div class="modal-step">
                        <span class="step-badge">5</span>
                        <div class="step-content">
                            Revenez ici et cliquez sur <strong>📥 Importer résultats IA (JSON)</strong> pour charger le fichier et afficher les résultats.
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    `;
}

// =========================================================================
// ENTRY POINT
// =========================================================================
export async function render() {
    await requireAuth();

    const root = document.getElementById('appRoot');
    root.innerHTML = `
        <section class="scraper-page">
            <div class="server-status-banner card hidden" id="serverStatusBanner">
                <span class="warning-icon">⚠️</span>
                <div>
                    <h3>Serveur local non détecté</h3>
                    <p>Le scraper Playwright nécessite <code>server.py</code> lancé sur ton ordinateur. <a href="/install" data-link>Voir le guide</a>.</p>
                </div>
            </div>
            ${scraperMarkup()}
        </section>
    `;

    // Banner si server.py n'est pas joignable
    const localOk = await checkLocalServer();
    if (!localOk) {
        document.getElementById('serverStatusBanner').classList.remove('hidden');
    }

    // Brancher la logique d'origine
    initScraperLogic();
    initPublishButton();
}

// =========================================================================
// LOGIQUE SCRAPER — migrée depuis l'ancien app.js
// Adaptations :
//  - Tous les fetch('/api/...') deviennent fetch(`${API}/api/...`)
//  - L'EventSource utilise l'URL absolue API + /api/events
//  - On expose window.allResults / lastModelUsed / lastCriteria / lastUrl
//    pour que initPublishButton() puisse y accéder.
//  - Quand l'état devient 'completed' (ou après import JSON OK), on dévoile #publishArea
// =========================================================================
function initScraperLogic() {
    let allResults = [];
    let activeJobStatus = 'idle';
    let eventSource = null;

    const statusDot = document.getElementById('statusDot');
    const statusLabel = document.getElementById('statusLabel');
    const configForm = document.getElementById('configForm');
    const urlInput = document.getElementById('urlInput');
    const pagesInput = document.getElementById('pagesInput');
    const delayInput = document.getElementById('delayInput');
    const criteresInput = document.getElementById('criteresInput');
    const btnStart = document.getElementById('btnStart');
    const btnStop = document.getElementById('btnStop');
    const btnResume = document.getElementById('btnResume');
    const captchaBanner = document.getElementById('captchaBanner');

    const welcomeView = document.getElementById('welcomeView');
    const progressView = document.getElementById('progressView');
    const resultsView = document.getElementById('resultsView');

    const progressStateText = document.getElementById('progressStateText');
    const progressBar = document.getElementById('progressBar');
    const consoleLogs = document.getElementById('consoleLogs');
    const btnClearConsole = document.getElementById('btnClearConsole');

    const liveTabButtons = document.querySelectorAll('.live-tab');
    const consolePanel = document.getElementById('consolePanel');
    const livePanel = document.getElementById('livePanel');
    const liveResultsGrid = document.getElementById('liveResultsGrid');
    const liveCount = document.getElementById('liveCount');
    const liveEmpty = document.getElementById('liveEmpty');
    let liveItemsCount = 0;

    const filterSearch = document.getElementById('filterSearch');
    const filterMinScore = document.getElementById('filterMinScore');
    const sortSelector = document.getElementById('sortSelector');
    const resultsGrid = document.getElementById('resultsGrid');
    const noResultsAlert = document.getElementById('noResultsAlert');

    const statTotalCount = document.getElementById('statTotalCount');
    const statBestScore = document.getElementById('statBestScore');
    const statMinPrice = document.getElementById('statMinPrice');

    const claudeStepArea = document.getElementById('claudeStepArea');
    const downloadRawLink = document.getElementById('downloadRawLink');

    // --- Download brut.json ---
    if (downloadRawLink) {
        downloadRawLink.addEventListener('click', (e) => {
            e.preventDefault();
            window.open(`${API}/api/raw-ads`, '_blank');
        });
    }

    // --- Détection scrape déjà existant (au load de la page) ---
    async function refreshScrapedInfo() {
        try {
            const response = await fetch(`${API}/api/scraped-info`);
            const data = await response.json();
            if (data.count > 0) {
                // Un brut.json existe déjà → affiche le panneau Claude.ai pour qu'on puisse importer
                claudeStepArea.classList.remove('hidden');
            }
        } catch (error) { /* serveur local off */ }
    }

    // --- SSE ---
    function connectSSE() {
        if (eventSource) eventSource.close();
        eventSource = new EventSource(`${API}/api/events`);
        eventSource.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.type === 'status') updateUIState(data.status);
            else if (data.type === 'log') { addLogLine(data.message); updateProgressBarFromLog(data.message); }
            else if (data.type === 'result_item') addLiveResult(data.item, data.index, data.total);
            else if (data.type === 'results') { allResults = data.results; window.__scraperState.allResults = allResults; displayResults(); }
        };
        eventSource.onerror = () => {
            statusDot.className = 'status-dot status-error';
            statusLabel.textContent = 'Déconnecté du backend';
        };
        // Stocker pour cleanup à la sortie de la page
        window.__scraperEventSource = eventSource;
    }

    // --- UI state ---
    function updateUIState(status) {
        activeJobStatus = status;
        statusDot.className = 'status-dot';
        const publishArea = document.getElementById('publishArea');
        switch (status) {
            case 'idle':
                statusDot.classList.add('status-idle'); statusLabel.textContent = 'Prêt / Inactif';
                btnStart.disabled = false; btnStop.disabled = true; captchaBanner.classList.add('hidden');
                showView(allResults.length === 0 ? 'welcome' : 'results');
                if (allResults.length > 0) publishArea?.classList.remove('hidden');
                break;
            case 'scraping':
                statusDot.classList.add('status-running'); statusLabel.textContent = 'Scraping LBC...';
                progressStateText.textContent = 'Récupération des annonces Leboncoin...';
                btnStart.disabled = true; btnStop.disabled = false; captchaBanner.classList.add('hidden');
                showView('progress'); publishArea?.classList.add('hidden');
                break;
            case 'captcha_required':
                statusDot.classList.add('status-captcha'); statusLabel.textContent = 'En attente de Captcha';
                progressStateText.textContent = 'Bloqué par Datadome - Résolution requise';
                btnStart.disabled = true; btnStop.disabled = false; captchaBanner.classList.remove('hidden');
                showView('progress');
                break;
            case 'scraped':
                // Scrape terminé, brut.json prêt → invite à utiliser Claude.ai
                statusDot.classList.add('status-done'); statusLabel.textContent = 'Scrape terminé';
                progressBar.style.width = '70%';
                progressStateText.textContent = 'Annonces scrapées, prêtes pour Claude.ai';
                btnStart.disabled = false; btnStop.disabled = true; captchaBanner.classList.add('hidden');
                claudeStepArea.classList.remove('hidden');
                window.__scraperState.scrapedAt = new Date().toISOString();
                break;
            case 'completed':
                // JSON Claude.ai importé → résultats analysés affichés + publish dispo
                statusDot.classList.add('status-done'); statusLabel.textContent = 'Terminé';
                progressBar.style.width = '100%';
                btnStart.disabled = false; btnStop.disabled = true; captchaBanner.classList.add('hidden');
                showView('results');
                claudeStepArea.classList.remove('hidden'); // garde l'option de réimporter
                publishArea?.classList.remove('hidden');
                if (!window.__scraperState.scrapedAt) {
                    window.__scraperState.scrapedAt = new Date().toISOString();
                }
                break;
            case 'error':
                statusDot.classList.add('status-error'); statusLabel.textContent = 'Erreur fatale';
                btnStart.disabled = false; btnStop.disabled = true; captchaBanner.classList.add('hidden');
                showView('progress');
                break;
        }
    }

    function showView(viewName) {
        welcomeView.classList.add('hidden');
        progressView.classList.add('hidden');
        resultsView.classList.add('hidden');
        if (viewName === 'welcome')  welcomeView.classList.remove('hidden');
        else if (viewName === 'progress') progressView.classList.remove('hidden');
        else if (viewName === 'results')  resultsView.classList.remove('hidden');
    }

    // --- Console ---
    function addLogLine(text, customClass = '') {
        const line = document.createElement('div');
        line.classList.add('log-line');
        if (customClass) line.classList.add(customClass);
        else if (text.includes('⚠️') || text.includes('[BLOCAGE]') || text.includes('d\'arrêt')) line.classList.add('log-warn');
        else if (text.includes('🔴') || text.includes('Erreur')) line.classList.add('log-error');
        else if (text.includes('✅') || text.includes('Gardée') || text.includes('terminé') || text.includes('complété')) line.classList.add('log-success');
        else if (text.includes('🤖') || text.includes('Analyse') || text.includes('Lancement')) line.classList.add('log-info');
        else line.classList.add('log-system');
        line.textContent = text.startsWith('>') ? text : '> ' + text;
        consoleLogs.appendChild(line);
        consoleLogs.scrollTop = consoleLogs.scrollHeight;
    }

    function updateProgressBarFromLog(text) {
        const scrapeMatch = text.match(/page de recherche (\d+)\/(\d+)/i) || text.match(/page (\d+)\/(\d+)/i);
        if (scrapeMatch) {
            const current = parseInt(scrapeMatch[1], 10);
            const total = parseInt(scrapeMatch[2], 10);
            progressBar.style.width = `${((current - 1) / total) * 45 + 5}%`;
        }
        const aiMatch = text.match(/Analyse (\d+)\/(\d+)\s*:/i);
        if (aiMatch) {
            const current = parseInt(aiMatch[1], 10);
            const total = parseInt(aiMatch[2], 10);
            progressBar.style.width = `${50 + (current / total) * 45}%`;
        }
    }

    btnClearConsole.addEventListener('click', () => {
        consoleLogs.innerHTML = '<div class="log-line log-system">> Console vidée.</div>';
    });

    // --- Form actions ---
    configForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        if (['scraping', 'captcha_required'].includes(activeJobStatus)) return;
        const payload = {
            url: urlInput.value.trim(),
            pages: parseInt(pagesInput.value, 10) || 1,
            delay: parseInt(delayInput.value, 10) || 1500,
            criteres: criteresInput.value.trim(),
        };
        if (!payload.url) {
            addLogLine('🔴 Erreur : l\'URL de recherche est obligatoire.', 'log-error');
            return;
        }
        if (!payload.criteres) {
            addLogLine('🔴 Erreur : les critères de recherche sont obligatoires.', 'log-error');
            return;
        }
        // Capturer les méta-données pour le publish ultérieur (D-01 : toujours cloud via Claude.ai)
        window.__scraperState.modelUsed = 'claude-3.5-sonnet';
        window.__scraperState.criteria = payload.criteres;
        window.__scraperState.sourceUrl = payload.url;

        progressBar.style.width = '0%';
        consoleLogs.innerHTML = '';
        allResults = [];
        window.__scraperState.allResults = allResults;
        resetLiveResults();
        switchLiveTab('console');
        addLogLine('🚀 Envoi de la commande de démarrage...');
        try {
            const response = await fetch(`${API}/api/start`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            const data = await response.json();
            if (response.ok) addLogLine('✅ Commande lancée avec succès.');
            else addLogLine(`🔴 Erreur : ${data.error || 'Impossible de démarrer'}`, 'log-error');
        } catch (error) {
            addLogLine('🔴 Échec de la communication avec le serveur. Lance server.py sur ton PC.', 'log-error');
        }
    });

    btnResume.addEventListener('click', async () => {
        addLogLine('✉️ Envoi du signal de reprise...');
        try {
            const response = await fetch(`${API}/api/resume`, { method: 'POST' });
            if (response.ok) { captchaBanner.classList.add('hidden'); addLogLine('✅ Signal de reprise envoyé.'); }
            else { const d = await response.json(); addLogLine(`⚠️ Échec de la reprise : ${d.error}`, 'log-warn'); }
        } catch (_) { addLogLine('🔴 Impossible de contacter le serveur.', 'log-error'); }
    });

    btnStop.addEventListener('click', async () => {
        addLogLine('🛑 Signal d\'arrêt demandé...');
        try {
            const response = await fetch(`${API}/api/stop`, { method: 'POST' });
            if (response.ok) addLogLine('✅ Commande d\'arrêt envoyée.');
            else { const d = await response.json(); addLogLine(`⚠️ Échec de l'arrêt : ${d.error}`, 'log-warn'); }
        } catch (_) { addLogLine('🔴 Erreur réseau pour arrêter le scraper.', 'log-error'); }
    });

    // --- Live tabs ---
    function switchLiveTab(tabName) {
        liveTabButtons.forEach(btn => btn.classList.toggle('active', btn.dataset.tab === tabName));
        consolePanel.classList.toggle('hidden', tabName !== 'console');
        livePanel.classList.toggle('hidden', tabName !== 'live');
    }
    liveTabButtons.forEach(btn => btn.addEventListener('click', () => switchLiveTab(btn.dataset.tab)));

    function resetLiveResults() {
        liveItemsCount = 0;
        liveResultsGrid.innerHTML = '';
        liveCount.textContent = '0';
        liveEmpty.classList.remove('hidden');
    }

    function escapeAttr(text) { return String(text || '').replace(/"/g, '&quot;'); }
    function scoreClassFor(note) {
        const n = parseFloat(note) || 0;
        if (n >= 80) return 'score-high';
        if (n >= 60) return 'score-medium';
        return 'score-low';
    }
    function buildCardMarkup(item) {
        const scoreClass = scoreClassFor(item.note_sur_100);
        return `
            <div class="card-top">
                <div class="card-price">${item.prix} €</div>
                <div class="card-score ${scoreClass}">⭐ ${item.note_sur_100}/100</div>
            </div>
            <div class="card-title" title="${escapeAttr(item.titre)}">${item.titre}</div>
            <div class="card-tags">
                <span class="card-tag">🔍 ${item.caracteristiques}</span>
            </div>
            <div class="card-analysis">
                <span class="analysis-label">🤖 Justification IA</span>
                ${item.explication}
            </div>
            <a href="${item.url}" target="_blank" rel="noopener" class="btn-card">Voir sur Leboncoin 🔗</a>
        `;
    }
    function addLiveResult(item, index, total) {
        if (!item) return;
        allResults.push(item);
        window.__scraperState.allResults = allResults;
        liveEmpty.classList.add('hidden');
        const card = document.createElement('div');
        card.className = 'result-card live-pop';
        card.innerHTML = buildCardMarkup(item);
        liveResultsGrid.insertBefore(card, liveResultsGrid.firstChild);
        liveItemsCount += 1;
        liveCount.textContent = total ? `${liveItemsCount}/${total}` : String(liveItemsCount);
    }

    function displayResults() {
        if (!allResults || allResults.length === 0) {
            statTotalCount.textContent = '0';
            statBestScore.textContent = '0/100';
            statMinPrice.textContent = '0 €';
            resultsGrid.innerHTML = '';
            noResultsAlert.classList.remove('hidden');
            return;
        }
        const searchText = filterSearch.value.toLowerCase().trim();
        const minScore = parseFloat(filterMinScore.value);
        const sortBy = sortSelector.value;
        let filtered = allResults.filter(item => {
            const matchesText = (item.titre || '').toLowerCase().includes(searchText) ||
                (item.caracteristiques || '').toLowerCase().includes(searchText) ||
                (item.explication || '').toLowerCase().includes(searchText);
            const scoreVal = parseFloat(item.note_sur_100) || 0;
            return matchesText && scoreVal >= minScore;
        });
        if (sortBy === 'note-desc')  filtered.sort((a, b) => b.note_sur_100 - a.note_sur_100);
        if (sortBy === 'price-asc')  filtered.sort((a, b) => a.prix - b.prix);
        if (sortBy === 'price-desc') filtered.sort((a, b) => b.prix - a.prix);
        const rawNotes  = allResults.map(i => parseFloat(i.note_sur_100) || 0);
        const rawPrices = allResults.map(i => parseFloat(i.prix) || 0);
        statTotalCount.textContent = allResults.length;
        statBestScore.textContent  = `${Math.max(...rawNotes, 0)}/100`;
        statMinPrice.textContent   = `${Math.min(...rawPrices, 0)} €`;
        resultsGrid.innerHTML = '';
        if (filtered.length === 0) { noResultsAlert.classList.remove('hidden'); return; }
        noResultsAlert.classList.add('hidden');
        filtered.forEach(item => {
            const card = document.createElement('div');
            card.className = 'result-card';
            card.innerHTML = buildCardMarkup(item);
            resultsGrid.appendChild(card);
        });
    }
    filterSearch.addEventListener('input', displayResults);
    filterMinScore.addEventListener('change', displayResults);
    sortSelector.addEventListener('change', displayResults);

    // --- Modale prompt IA ---
    const btnShowPrompt   = document.getElementById('btnShowPrompt');
    const promptModal     = document.getElementById('promptModal');
    const btnCloseModal   = document.getElementById('btnCloseModal');
    const generatedPrompt = document.getElementById('generatedPrompt');
    const btnCopyPrompt   = document.getElementById('btnCopyPrompt');
    const copyPromptIcon  = document.getElementById('copyPromptIcon');
    const copyPromptText  = document.getElementById('copyPromptText');

    function buildPromptText(criteres) {
        const criteresText = criteres.trim() || '(aucun critère saisi — renseignez vos critères dans le formulaire avant d\'ouvrir cette fenêtre)';
        return `Tu es un expert intraitable en évaluation d'annonces de seconde main.
Je te fournis un fichier JSON (leboncoin_brut.json) contenant des annonces Leboncoin scrapées.

Mes critères de recherche : ${criteresText}

RÈGLES IMPORTANTES :
1. Analyse TOUTES les annonces du fichier sans exception. Les annonces qui ne correspondent pas aux critères reçoivent une note proche de 0 — elles ne sont pas ignorées.
2. Pour chaque annonce, identifie le modèle exact du produit et déduis les caractéristiques manquantes grâce à tes connaissances (fiches techniques constructeur). N'écris jamais "inconnu" ou "non précisé" si le modèle te permet de le déduire.
3. Attribue une note décimale de 0 à 100 au rapport qualité/prix. Utilise des décimales (ex : 84.5, 91.2, 78.7) pour différencier finement les annonces — évite absolument les notes rondes identiques.
4. Dans les valeurs texte du JSON, n'utilise JAMAIS de vrais retours à la ligne (touche Entrée). Écris \\n si tu veux en simuler un.
5. Renvoie le tableau JSON COMPLET en une seule réponse, sans aucun texte avant ou après.

Format exact attendu (renvoie directement le tableau, commence par [ sans introduction) :
[
  {
    "titre": "titre exact de l'annonce",
    "prix": prix_numérique,
    "url": "url_complète_de_l_annonce",
    "note_sur_100": note_décimale_0_à_100,
    "caracteristiques": "résumé court des specs clés identifiées ou déduites du modèle",
    "explication": "justification précise de la note : adéquation aux critères, état, rapport qualité/prix",
    "match_criteres": true
  }
]`;
    }

    function openPromptModal() {
        generatedPrompt.value = buildPromptText(criteresInput ? criteresInput.value : '');
        promptModal.classList.remove('hidden');
        btnCopyPrompt.classList.remove('copied');
        copyPromptIcon.textContent = '📋';
        if (copyPromptText) copyPromptText.textContent = ' Copier le prompt';
    }
    function closePromptModal() { promptModal.classList.add('hidden'); }
    if (btnShowPrompt) btnShowPrompt.addEventListener('click', openPromptModal);
    if (btnCloseModal) btnCloseModal.addEventListener('click', closePromptModal);
    if (promptModal) promptModal.addEventListener('click', (e) => { if (e.target === promptModal) closePromptModal(); });
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && promptModal && !promptModal.classList.contains('hidden')) closePromptModal();
    });
    if (btnCopyPrompt) {
        btnCopyPrompt.addEventListener('click', async () => {
            try { await navigator.clipboard.writeText(generatedPrompt.value); }
            catch { generatedPrompt.select(); document.execCommand('copy'); }
            btnCopyPrompt.classList.add('copied');
            copyPromptIcon.textContent = '✅';
            if (copyPromptText) copyPromptText.textContent = ' Copié !';
            setTimeout(() => {
                btnCopyPrompt.classList.remove('copied');
                copyPromptIcon.textContent = '📋';
                if (copyPromptText) copyPromptText.textContent = ' Copier le prompt';
            }, 2500);
        });
    }

    // --- Import JSON ---
    const btnImportResults = document.getElementById('btnImportResults');
    const importJsonFile = document.getElementById('importJsonFile');
    if (btnImportResults && importJsonFile) {
        btnImportResults.addEventListener('click', () => {
            importJsonFile.value = '';
            importJsonFile.click();
        });
        importJsonFile.addEventListener('change', async (e) => {
            const file = e.target.files[0];
            if (!file) return;
            btnImportResults.disabled = true;
            btnImportResults.innerHTML = '<span class="btn-icon">⏳</span> Import en cours...';
            try {
                const text = await file.text();
                let data;
                try { data = JSON.parse(text); }
                catch (parseErr) { throw new Error(`Fichier JSON invalide : ${parseErr.message}`); }
                if (!Array.isArray(data)) {
                    throw new Error('Le fichier doit contenir un tableau JSON d\'annonces ([ { ... }, ... ]).');
                }
                const response = await fetch(`${API}/api/import-results`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data),
                });
                if (response.ok) {
                    const result = await response.json();
                    addLogLine(`✅ Import réussi : ${result.count} annonces chargées depuis "${file.name}"`, 'log-success');
                    // Pour un import direct, on présume modèle cloud (l'user vient de coller du Claude.ai en général)
                    window.__scraperState.modelUsed = window.__scraperState.modelUsed || 'claude-3.5-sonnet';
                    window.__scraperState.criteria = (criteresInput?.value || '').trim() || '(import JSON)';
                    window.__scraperState.scrapedAt = new Date().toISOString();
                } else {
                    const err = await response.json();
                    throw new Error(err.error || 'Erreur serveur inconnue');
                }
            } catch (error) {
                addLogLine(`🔴 Erreur lors de l'import : ${error.message}`, 'log-error');
            } finally {
                btnImportResults.disabled = false;
                btnImportResults.innerHTML = '<span class="btn-icon">📥</span> Importer le JSON Claude.ai';
            }
        });
    }

    // === BOOTSTRAP ===
    window.__scraperState = {
        allResults: [],
        modelUsed: 'claude-3.5-sonnet',  // D-01 : workflow forcé Claude.ai
        criteria: '',
        sourceUrl: null,
        scrapedAt: null,
    };
    connectSSE();
    refreshScrapedInfo();
}

// =========================================================================
// PUBLISH BUTTON
// =========================================================================
function initPublishButton() {
    const btn = document.getElementById('btnPublish');
    if (!btn) return;
    btn.addEventListener('click', async () => {
        const titleEl  = document.getElementById('publishTitle');
        const statusEl = document.getElementById('publishStatus');
        const state = window.__scraperState || {};
        const results = state.allResults || [];

        if (results.length === 0) {
            statusEl.textContent = '⚠️ Aucun résultat à publier.';
            statusEl.className = 'publish-status warn';
            return;
        }

        const title = titleEl.value.trim() || `Recherche du ${new Date().toLocaleDateString('fr-FR')}`;
        const modelName = state.modelUsed || 'inconnu';

        btn.disabled = true;
        statusEl.textContent = '⏳ Publication…';
        statusEl.className = 'publish-status';

        try {
            const searchId = await publishSearch({
                title,
                criteria: state.criteria || '',
                source_url: state.sourceUrl || null,
                platform: 'leboncoin',
                model_name: modelName,
                model_type: inferModelType(modelName),
                scraped_at: state.scrapedAt,
                listings: results,
            });
            statusEl.innerHTML = `✅ Publiée ! <a href="/search/${searchId}" data-link>Voir la recherche</a>`;
            statusEl.className = 'publish-status success';
            titleEl.value = '';
        } catch (err) {
            statusEl.textContent = `❌ ${err.message}`;
            statusEl.className = 'publish-status error';
            btn.disabled = false;
        }
    });
}
