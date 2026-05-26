document.addEventListener('DOMContentLoaded', () => {
    // Check if opened via file:// protocol (direct HTML double-click)
    if (window.location.protocol === 'file:') {
        const fileWarning = document.getElementById('fileProtocolWarning');
        if (fileWarning) {
            fileWarning.classList.remove('hidden');
            
            // Copy URL functionality
            const btnCopyUrl = document.getElementById('btnCopyUrl');
            const warningUrlInput = document.getElementById('warningUrlInput');
            btnCopyUrl.addEventListener('click', () => {
                warningUrlInput.select();
                document.execCommand('copy');
                btnCopyUrl.textContent = 'Copié !';
                setTimeout(() => { btnCopyUrl.textContent = 'Copier l\'URL'; }, 2000);
            });
        }
        return; // Stop execution
    }

    // Global data stores
    let allResults = [];
    let activeJobStatus = 'idle';
    let eventSource = null;

    // DOM Elements
    const statusDot = document.getElementById('statusDot');
    const statusLabel = document.getElementById('statusLabel');
    const configForm = document.getElementById('configForm');
    const urlInput = document.getElementById('urlInput');
    const pagesInput = document.getElementById('pagesInput');
    const delayInput = document.getElementById('delayInput');
    const modelSelect = document.getElementById('modelSelect');
    const criteresInput = document.getElementById('criteresInput');
    const reuseScrapedInput = document.getElementById('reuseScrapedInput');
    const reuseScrapedHint = document.getElementById('reuseScrapedHint');
    const btnStart = document.getElementById('btnStart');
    const btnStop = document.getElementById('btnStop');
    const btnResume = document.getElementById('btnResume');
    const captchaBanner = document.getElementById('captchaBanner');

    // View Panels
    const welcomeView = document.getElementById('welcomeView');
    const progressView = document.getElementById('progressView');
    const resultsView = document.getElementById('resultsView');

    // Progress elements
    const progressStateText = document.getElementById('progressStateText');
    const progressBar = document.getElementById('progressBar');
    const consoleLogs = document.getElementById('consoleLogs');
    const btnClearConsole = document.getElementById('btnClearConsole');

    // Live notation tab elements
    const liveTabButtons = document.querySelectorAll('.live-tab');
    const consolePanel = document.getElementById('consolePanel');
    const livePanel = document.getElementById('livePanel');
    const liveResultsGrid = document.getElementById('liveResultsGrid');
    const liveCount = document.getElementById('liveCount');
    const liveEmpty = document.getElementById('liveEmpty');
    let liveItemsCount = 0;

    // Filter elements
    const filterSearch = document.getElementById('filterSearch');
    const filterMinScore = document.getElementById('filterMinScore');
    const sortSelector = document.getElementById('sortSelector');
    const resultsGrid = document.getElementById('resultsGrid');
    const noResultsAlert = document.getElementById('noResultsAlert');

    // Stats elements
    const statTotalCount = document.getElementById('statTotalCount');
    const statBestScore = document.getElementById('statBestScore');
    const statMinPrice = document.getElementById('statMinPrice');

    // --- INITIALIZE & FETCH MODELS ---

    const btnRefreshModels = document.getElementById('btnRefreshModels');
    const modelsStatus = document.getElementById('modelsStatus');

    async function loadModels() {
        modelSelect.innerHTML = '<option value="" disabled selected>Chargement...</option>';
        if (btnRefreshModels) btnRefreshModels.disabled = true;
        if (modelsStatus) modelsStatus.textContent = '';
        try {
            const response = await fetch('/api/models');
            const data = await response.json();

            modelSelect.innerHTML = '';
            if (data.models && data.models.length > 0 && !data.fallback) {
                data.models.forEach(model => {
                    const option = document.createElement('option');
                    option.value = model;
                    option.textContent = model;
                    modelSelect.appendChild(option);
                });
                if (modelsStatus) modelsStatus.textContent = `✅ ${data.models.length} modèle(s) Ollama chargé(s).`;
            } else if (data.fallback) {
                modelSelect.innerHTML = '<option value="">⚠️ Ollama inaccessible — sélectionnez un modèle manuellement</option>';
                if (modelsStatus) modelsStatus.innerHTML = '⚠️ Ollama n\'est pas joignable. Lancez Ollama puis cliquez 🔄 pour recharger.';
            } else {
                modelSelect.innerHTML = '<option value="">Aucun modèle trouvé</option>';
                if (modelsStatus) modelsStatus.textContent = 'Aucun modèle installé dans Ollama.';
            }
        } catch (error) {
            console.error('Erreur chargement modèles Ollama:', error);
            modelSelect.innerHTML = '<option value="">⚠️ Erreur de connexion à Ollama</option>';
            if (modelsStatus) modelsStatus.innerHTML = '⚠️ Impossible de joindre Ollama. Lancez-le puis cliquez 🔄.';
        } finally {
            if (btnRefreshModels) btnRefreshModels.disabled = false;
        }
    }

    if (btnRefreshModels) {
        btnRefreshModels.addEventListener('click', loadModels);
    }

    loadModels();
    connectSSE();
    refreshScrapedInfo();

    // --- RÉ-ANALYSE DES ANNONCES DÉJÀ SCRAPÉES ---

    async function refreshScrapedInfo() {
        let count = 0;
        try {
            const response = await fetch('/api/scraped-info');
            const data = await response.json();
            count = data.count || 0;
        } catch (error) {
            console.error('Erreur info annonces en cache:', error);
        }

        if (count > 0) {
            reuseScrapedInput.disabled = false;
            reuseScrapedHint.textContent = `Ne re-scrape pas : ré-utilise les ${count} annonces du dernier lot et applique tes nouveaux critères / réglages IA.`;
        } else {
            reuseScrapedInput.disabled = true;
            reuseScrapedInput.checked = false;
            reuseScrapedHint.textContent = 'Aucun lot déjà scrapé pour le moment. Lance d\'abord une recherche complète.';
        }
        applyReuseState();
    }

    function applyReuseState() {
        // En mode ré-analyse, l'URL et les pages ne servent pas : on les rend optionnels.
        const reuse = reuseScrapedInput.checked && !reuseScrapedInput.disabled;
        urlInput.required = !reuse;
        urlInput.disabled = reuse;
        pagesInput.disabled = reuse;
        delayInput.disabled = reuse;
    }

    reuseScrapedInput.addEventListener('change', applyReuseState);

    // --- SSE CONNECTION ---

    function connectSSE() {
        if (eventSource) {
            eventSource.close();
        }

        eventSource = new EventSource('/api/events');

        eventSource.onmessage = (event) => {
            const data = JSON.parse(event.data);
            
            if (data.type === 'status') {
                updateUIState(data.status);
            } else if (data.type === 'log') {
                addLogLine(data.message);
                updateProgressBarFromLog(data.message);
            } else if (data.type === 'result_item') {
                addLiveResult(data.item, data.index, data.total);
            } else if (data.type === 'results') {
                allResults = data.results;
                displayResults();
            }
        };

        eventSource.onerror = (err) => {
            console.error('SSE connection error:', err);
            statusDot.className = 'status-dot status-error';
            statusLabel.textContent = 'Déconnecté du backend';
        };
    }

    // --- UI STATE MANAGEMENT ---

    function updateUIState(status) {
        activeJobStatus = status;
        
        // Reset classes
        statusDot.className = 'status-dot';
        
        switch(status) {
            case 'idle':
                statusDot.classList.add('status-idle');
                statusLabel.textContent = 'Prêt / Inactif';
                
                btnStart.disabled = false;
                btnStop.disabled = true;
                captchaBanner.classList.add('hidden');
                
                // Show welcome view if we have no results, otherwise keep results
                if (allResults.length === 0) {
                    showView('welcome');
                } else {
                    showView('results');
                }
                break;
                
            case 'scraping':
                statusDot.classList.add('status-running');
                statusLabel.textContent = 'Scraping LBC...';
                progressStateText.textContent = 'Récupération des annonces Leboncoin...';
                
                btnStart.disabled = true;
                btnStop.disabled = false;
                captchaBanner.classList.add('hidden');
                showView('progress');
                break;
                
            case 'captcha_required':
                statusDot.classList.add('status-captcha');
                statusLabel.textContent = 'En attente de Captcha';
                progressStateText.textContent = 'Bloqué par Datadome - Résolution requise';
                
                btnStart.disabled = true;
                btnStop.disabled = false;
                captchaBanner.classList.remove('hidden');
                showView('progress');
                break;
                
            case 'analyzing':
                statusDot.classList.add('status-running');
                statusLabel.textContent = 'Analyse IA...';
                progressStateText.textContent = 'Analyse des descriptions par l\'IA locale...';

                btnStart.disabled = true;
                btnStop.disabled = false;
                captchaBanner.classList.add('hidden');
                showView('progress');
                switchLiveTab('live');
                break;
                
            case 'completed':
                statusDot.classList.add('status-done');
                statusLabel.textContent = 'Terminé';
                progressBar.style.width = '100%';
                
                btnStart.disabled = false;
                btnStop.disabled = true;
                captchaBanner.classList.add('hidden');
                showView('results');
                refreshScrapedInfo();
                break;

            case 'error':
                statusDot.classList.add('status-error');
                statusLabel.textContent = 'Erreur fatale';
                
                btnStart.disabled = false;
                btnStop.disabled = true;
                captchaBanner.classList.add('hidden');
                showView('progress');
                break;
        }
    }

    function showView(viewName) {
        welcomeView.classList.add('hidden');
        progressView.classList.add('hidden');
        resultsView.classList.add('hidden');

        if (viewName === 'welcome') {
            welcomeView.classList.remove('hidden');
        } else if (viewName === 'progress') {
            progressView.classList.remove('hidden');
        } else if (viewName === 'results') {
            resultsView.classList.remove('hidden');
        }
    }

    // --- CONSOLE & LOG HANDLING ---

    function addLogLine(text, customClass = '') {
        const line = document.createElement('div');
        line.classList.add('log-line');
        
        // Auto-styling based on contents
        if (customClass) {
            line.classList.add(customClass);
        } else if (text.includes('⚠️') || text.includes('[BLOCAGE]') || text.includes('d\'arrêt')) {
            line.classList.add('log-warn');
        } else if (text.includes('🔴') || text.includes('Erreur')) {
            line.classList.add('log-error');
        } else if (text.includes('✅') || text.includes('Gardée') || text.includes('terminé') || text.includes('complété')) {
            line.classList.add('log-success');
        } else if (text.includes('🤖') || text.includes('Analyse') || text.includes('Lancement')) {
            line.classList.add('log-info');
        } else {
            line.classList.add('log-system');
        }
        
        line.textContent = text.startsWith('>') ? text : '> ' + text;
        consoleLogs.appendChild(line);
        consoleLogs.scrollTop = consoleLogs.scrollHeight;
    }

    function updateProgressBarFromLog(text) {
        // Parse "page X/Y" for scraping progress (ranges 0% - 50%)
        const scrapeMatch = text.match(/page de recherche (\d+)\/(\d+)/i) || text.match(/page (\d+)\/(\d+)/i);
        if (scrapeMatch) {
            const current = parseInt(scrapeMatch[1], 10);
            const total = parseInt(scrapeMatch[2], 10);
            const percent = ((current - 1) / total) * 45 + 5; // offset 5% start
            progressBar.style.width = `${percent}%`;
        }

        // Parse "Analyse X/Y" for AI analysis progress (ranges 50% - 95%)
        const aiMatch = text.match(/Analyse (\d+)\/(\d+)\s*:/i);
        if (aiMatch) {
            const current = parseInt(aiMatch[1], 10);
            const total = parseInt(aiMatch[2], 10);
            const percent = 50 + (current / total) * 45;
            progressBar.style.width = `${percent}%`;
        }
    }

    btnClearConsole.addEventListener('click', () => {
        consoleLogs.innerHTML = '<div class="log-line log-system">> Console vidée.</div>';
    });

    // --- FORM ACTIONS (START / RESUME / STOP) ---

    configForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        if (activeJobStatus === 'scraping' || activeJobStatus === 'captcha_required' || activeJobStatus === 'analyzing') {
            return;
        }

        const reuse = reuseScrapedInput.checked && !reuseScrapedInput.disabled;
        const payload = {
            url: urlInput.value.trim(),
            pages: parseInt(pagesInput.value, 10) || 1,
            delay: parseInt(delayInput.value, 10) || 1500,
            criteres: criteresInput.value.trim(),
            model: modelSelect.value,
            reuseScraped: reuse
        };

        if (!reuse && !payload.url) {
            addLogLine('🔴 Erreur : l\'URL de recherche est obligatoire (ou cochez la ré-analyse).', 'log-error');
            return;
        }
        if (!payload.criteres) {
            addLogLine('🔴 Erreur : les critères de recherche sont obligatoires.', 'log-error');
            return;
        }

        // Reset visual progress
        progressBar.style.width = '0%';
        consoleLogs.innerHTML = '';
        allResults = [];
        resetLiveResults();
        switchLiveTab('console');
        addLogLine('🚀 Envoi de la commande de démarrage...');

        try {
            const response = await fetch('/api/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await response.json();
            
            if (response.ok) {
                addLogLine('✅ Commande lancée avec succès.');
            } else {
                addLogLine(`🔴 Erreur : ${data.error || 'Impossible de démarrer'}`, 'log-error');
            }
        } catch (error) {
            console.error('Error starting job:', error);
            addLogLine('🔴 Échec de la communication avec le serveur.', 'log-error');
        }
    });

    btnResume.addEventListener('click', async () => {
        addLogLine('✉️ Envoi du signal de reprise...');
        try {
            const response = await fetch('/api/resume', { method: 'POST' });
            if (response.ok) {
                captchaBanner.classList.add('hidden');
                addLogLine('✅ Signal de reprise envoyé au navigateur.');
            } else {
                const data = await response.json();
                addLogLine(`⚠️ Échec de la reprise : ${data.error}`, 'log-warn');
            }
        } catch (error) {
            console.error('Error resuming job:', error);
            addLogLine('🔴 Impossible de contacter le serveur.', 'log-error');
        }
    });

    btnStop.addEventListener('click', async () => {
        addLogLine('🛑 Signal d\'arrêt demandé...');
        try {
            const response = await fetch('/api/stop', { method: 'POST' });
            if (response.ok) {
                addLogLine('✅ Commande d\'arrêt envoyée.');
            } else {
                const data = await response.json();
                addLogLine(`⚠️ Échec de l'arrêt : ${data.error}`, 'log-warn');
            }
        } catch (error) {
            console.error('Error stopping job:', error);
            addLogLine('🔴 Erreur réseau pour arrêter le scraper.', 'log-error');
        }
    });

    // --- LIVE NOTATION TAB ---

    function switchLiveTab(tabName) {
        liveTabButtons.forEach(btn => {
            btn.classList.toggle('active', btn.dataset.tab === tabName);
        });
        consolePanel.classList.toggle('hidden', tabName !== 'console');
        livePanel.classList.toggle('hidden', tabName !== 'live');
    }

    liveTabButtons.forEach(btn => {
        btn.addEventListener('click', () => switchLiveTab(btn.dataset.tab));
    });

    function resetLiveResults() {
        liveItemsCount = 0;
        liveResultsGrid.innerHTML = '';
        liveCount.textContent = '0';
        liveEmpty.classList.remove('hidden');
    }

    function escapeAttr(text) {
        return String(text || '').replace(/"/g, '&quot;');
    }

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
            <a href="${item.url}" target="_blank" class="btn-card">
                Voir sur Leboncoin 🔗
            </a>
        `;
    }

    function addLiveResult(item, index, total) {
        if (!item) return;
        allResults.push(item);
        liveEmpty.classList.add('hidden');

        const card = document.createElement('div');
        card.className = 'result-card live-pop';
        card.innerHTML = buildCardMarkup(item);
        // La plus récemment examinée s'affiche en haut : on voit l'IA avancer.
        liveResultsGrid.insertBefore(card, liveResultsGrid.firstChild);

        liveItemsCount += 1;
        liveCount.textContent = total ? `${liveItemsCount}/${total}` : String(liveItemsCount);
    }

    // --- DISPLAY RESULTS & LOCAL FILTERS ---

    function displayResults() {
        if (!allResults || allResults.length === 0) {
            statTotalCount.textContent = '0';
            statBestScore.textContent = '0/100';
            statMinPrice.textContent = '0 €';
            resultsGrid.innerHTML = '';
            noResultsAlert.classList.remove('hidden');
            return;
        }

        // Apply filters
        const searchText = filterSearch.value.toLowerCase().trim();
        const minScore = parseFloat(filterMinScore.value);
        const sortBy = sortSelector.value;

        let filtered = allResults.filter(item => {
            const matchesText = item.titre.toLowerCase().includes(searchText) || 
                                item.caracteristiques.toLowerCase().includes(searchText) ||
                                item.explication.toLowerCase().includes(searchText);
            
            const scoreVal = parseFloat(item.note_sur_100) || 0;
            const matchesScore = scoreVal >= minScore;
            
            return matchesText && matchesScore;
        });

        // Apply local sort
        if (sortBy === 'note-desc') {
            filtered.sort((a, b) => b.note_sur_100 - a.note_sur_100);
        } else if (sortBy === 'price-asc') {
            filtered.sort((a, b) => a.prix - b.prix);
        } else if (sortBy === 'price-desc') {
            filtered.sort((a, b) => b.prix - a.prix);
        }

        // Update stats counters
        const rawNotes = allResults.map(i => parseFloat(i.note_sur_100) || 0);
        const rawPrices = allResults.map(i => parseFloat(i.prix) || 0);
        
        statTotalCount.textContent = allResults.length;
        statBestScore.textContent = `${Math.max(...rawNotes, 0)}/100`;
        statMinPrice.textContent = `${Math.min(...rawPrices, 0)} €`;

        // Render grid
        resultsGrid.innerHTML = '';
        if (filtered.length === 0) {
            noResultsAlert.classList.remove('hidden');
            return;
        }
        
        noResultsAlert.classList.add('hidden');

        filtered.forEach(item => {
            const card = document.createElement('div');
            card.className = 'result-card';
            card.innerHTML = buildCardMarkup(item);
            resultsGrid.appendChild(card);
        });
    }

    // Bind filters & sorting
    filterSearch.addEventListener('input', displayResults);
    filterMinScore.addEventListener('change', displayResults);
    sortSelector.addEventListener('change', displayResults);

    // --- MODALE : PROMPT POUR IA EN LIGNE ---

    const btnShowPrompt    = document.getElementById('btnShowPrompt');
    const promptModal      = document.getElementById('promptModal');
    const btnCloseModal    = document.getElementById('btnCloseModal');
    const generatedPrompt  = document.getElementById('generatedPrompt');
    const btnCopyPrompt    = document.getElementById('btnCopyPrompt');
    const copyPromptIcon   = document.getElementById('copyPromptIcon');
    const copyPromptText   = document.getElementById('copyPromptText');

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
        const criteres = criteresInput ? criteresInput.value : '';
        generatedPrompt.value = buildPromptText(criteres);
        promptModal.classList.remove('hidden');
        // Reset copy button state
        btnCopyPrompt.classList.remove('copied');
        copyPromptIcon.textContent = '📋';
        if (copyPromptText) copyPromptText.textContent = ' Copier le prompt';
    }

    function closePromptModal() {
        promptModal.classList.add('hidden');
    }

    if (btnShowPrompt)  btnShowPrompt.addEventListener('click', openPromptModal);
    if (btnCloseModal)  btnCloseModal.addEventListener('click', closePromptModal);

    // Fermer en cliquant sur l'overlay (hors de la carte)
    if (promptModal) {
        promptModal.addEventListener('click', (e) => {
            if (e.target === promptModal) closePromptModal();
        });
    }

    // Fermer avec Escape
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && promptModal && !promptModal.classList.contains('hidden')) {
            closePromptModal();
        }
    });

    if (btnCopyPrompt) {
        btnCopyPrompt.addEventListener('click', async () => {
            try {
                await navigator.clipboard.writeText(generatedPrompt.value);
            } catch {
                // Fallback pour les navigateurs sans clipboard API
                generatedPrompt.select();
                document.execCommand('copy');
            }
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

    // --- IMPORT JSON RESULTS (depuis Claude.ai ou autre source externe) ---

    const btnImportResults = document.getElementById('btnImportResults');
    const importJsonFile = document.getElementById('importJsonFile');

    if (btnImportResults && importJsonFile) {
        btnImportResults.addEventListener('click', () => {
            importJsonFile.value = ''; // reset pour permettre de ré-importer le même fichier
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
                try {
                    data = JSON.parse(text);
                } catch (parseErr) {
                    throw new Error(`Fichier JSON invalide : ${parseErr.message}`);
                }

                if (!Array.isArray(data)) {
                    throw new Error('Le fichier doit contenir un tableau JSON d\'annonces ([ { ... }, ... ]).');
                }

                const response = await fetch('/api/import-results', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });

                if (response.ok) {
                    const result = await response.json();
                    addLogLine(`✅ Import réussi : ${result.count} annonces chargées depuis "${file.name}"`, 'log-success');
                } else {
                    const err = await response.json();
                    throw new Error(err.error || 'Erreur serveur inconnue');
                }
            } catch (error) {
                addLogLine(`🔴 Erreur lors de l'import : ${error.message}`, 'log-error');
                console.error('Import error:', error);
            } finally {
                btnImportResults.disabled = false;
                btnImportResults.innerHTML = '<span class="btn-icon">📥</span> Importer résultats IA (JSON)';
            }
        });
    }
});
