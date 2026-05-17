/**
 * AI-Hints Unified Template Script
 * This script handles AI Hints rendering for ALL platforms (Desktop, AnkiDroid, AnkiMobile, Web).
 * 
 * If Python (addon) is detected, it enables full control (Generate, Clear, etc.).
 * Otherwise, it provides a standalone viewer for mobile.
 */
(function() {
    // 1. Configuration & Styling
    const STYLES = `
        .ai-hints-container { margin-top: 15px; padding: 12px; border: 1px dashed #aaa; border-radius: 10px; background-color: rgba(128,128,128,0.08); text-align: left; font-family: sans-serif; clear: both; }
        .ai-hints-btn-box { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 10px; justify-content: center; }
        .ai-hints-btn { padding: 6px 12px; cursor: pointer; border-radius: 6px; border: 1px solid #999; background-color: #f0f0f0; color: #222; font-size: 13px; font-weight: 500; transition: background 0.2s; -webkit-tap-highlight-color: transparent; }
        .ai-hints-btn:hover { background-color: #e0e0e0; }
        .ai-hints-btn:active { background-color: #d0d0d0; transform: translateY(1px); }
        .ai-hints-btn:disabled { opacity: 0.5; cursor: default; }
        .ai-hints-list, .ai-hints-hint-list { margin-top: 10px; padding-left: 20px; display: none; }
        .ai-hints-list li, .ai-hints-hint-list li { margin-bottom: 6px; line-height: 1.4; }
        .ai-hints-correct { border-left: 4px solid #2ecc71; background-color: rgba(46, 204, 113, 0.15); padding-left: 8px; font-weight: 600; border-radius: 0 4px 4px 0; }
        .nightMode .ai-hints-container { background-color: rgba(255,255,255,0.05); border-color: #555; }
        .nightMode .ai-hints-btn { background-color: #333; color: #eee; border-color: #666; }
        .nightMode .ai-hints-btn:hover { background-color: #444; }
        .ai-hints-title { font-weight: bold; margin-bottom: 4px; display: block; font-size: 0.9em; opacity: 0.8; }
        .ai-hints-json-view { margin-top: 10px; padding: 8px; background: rgba(0,0,0,0.05); border-radius: 5px; font-family: monospace; font-size: 11px; white-space: pre-wrap; overflow-x: auto; }
        .nightMode .ai-hints-json-view { background: rgba(255,255,255,0.05); }
        .ai-hints-btn-generating { animation: ai-hints-pulse 1.5s infinite; background: linear-gradient(90deg, #f8fafc, #dbeafe, #f8fafc); background-size: 200% 100%; color: #111827; border-color: #60a5fa; opacity: 1; }
        .nightMode .ai-hints-btn-generating { background: linear-gradient(90deg, #172554, #1d4ed8, #172554); background-size: 200% 100%; color: #ffffff; border-color: #93c5fd; opacity: 1; }
        @keyframes ai-hints-pulse { 0% { opacity: 0.7; } 50% { opacity: 1; } 100% { opacity: 0.7; } }
    `;

    // 2. State & Helpers
    const isAddonActive = !!window.aiHintsUiConfig;
    
    function getPersistence() {
        return {
            save: (key, val) => { try { sessionStorage.setItem('ai_hints_' + key, JSON.stringify(val)); } catch(e){} },
            get: (key) => { try { return JSON.parse(sessionStorage.getItem('ai_hints_' + key)); } catch(e){ return null; } }
        };
    }

    function isAnswerSide() {
        return !!document.getElementById('answer') || !!document.querySelector('.answer') || document.body.classList.contains('answer') || (window.aiHintsUiConfig && window.aiHintsUiConfig.is_answer_side);
    }

    function getCardOrd() {
        const cloze = document.querySelector('.cloze');
        if (cloze) {
            const match = cloze.className.match(/\bc(\d+)\b/);
            if (match) return parseInt(match[1]) - 1;
        }
        return window.aiHintsCurrentCard ? window.aiHintsCurrentCard.ord : 0;
    }

    function shuffle(array, seed) {
        let m = array.length, t, i;
        const random = () => {
            const x = Math.sin(seed++) * 10000;
            return x - Math.floor(x);
        };
        while (m) {
            i = Math.floor(random() * m--);
            t = array[m]; array[m] = array[i]; array[i] = t;
        }
        return array;
    }

    function renderMath(el) {
        if (typeof MathJax !== 'undefined') {
            try {
                if (typeof MathJax.typesetPromise === 'function') MathJax.typesetPromise([el]);
                else if (typeof MathJax.Hub !== 'undefined') MathJax.Hub.Queue(["Typeset", MathJax.Hub, el]);
            } catch (e) {}
        }
    }

    function renderSection(parent, title, items, isCorrectFn, seed) {
        if (!items || items.length === 0) return null;
        const label = document.createElement('span');
        label.className = 'ai-hints-title';
        label.textContent = title;
        parent.appendChild(label);
        const list = document.createElement('ul');
        list.className = title.toLowerCase().includes('hint') ? 'ai-hints-hint-list' : 'ai-hints-list';
        const listItems = items.map(text => {
            const li = document.createElement('li');
            li.textContent = text;
            if (isCorrectFn && isCorrectFn(text)) li.className = 'ai-hints-correct';
            return li;
        });
        if (title.toLowerCase().includes('option')) shuffle(listItems, seed);
        listItems.forEach(li => list.appendChild(li));
        parent.appendChild(list);
        return list;
    }

    function blockBelongsToCurrentCard(block, data, cardKey, cardId, ord) {
        if (!block || !isAddonActive) return true;

        const blockCardId = block.getAttribute ? block.getAttribute('data-ai-hints-card-id') : null;
        if (blockCardId && String(blockCardId) !== String(cardId)) return false;

        const blockOrd = block.getAttribute ? block.getAttribute('data-ai-hints-card-ord') : null;
        if (blockOrd !== null && blockOrd !== undefined && blockOrd !== '' && String(blockOrd) !== String(ord)) return false;

        const isKeyed = data && typeof data === 'object' && !Array.isArray(data) &&
            !data.hints && !data.options && Object.keys(data).some(key => /^c\d+$/.test(key));
        if (isKeyed && !data[cardKey]) return false;

        return true;
    }

    // 3. Main Init
    function init(manualData, isManualAction) {
        // manualData presence indicates an update from Python after generation
        const hasOverrideData = !!manualData;
        const jsonBlocks = document.querySelectorAll('.ai-hints-json');
        if (jsonBlocks.length === 0 && !hasOverrideData && !isAddonActive) return;

        // Cleanup any existing rendered containers to prevent duplicates
        document.querySelectorAll('.ai-hints-container').forEach(e => e.remove());
        document.querySelectorAll('.ai-hints-json').forEach(e => delete e.dataset.aiHintsRendered);

        // Configuration
        const uiCfg = window.aiHintsUiConfig || {};
        const mobileCfg = window.aiHintsMobileConfig || {};
        const useEmojis = !isAddonActive && mobileCfg.useEmojis;
        const showExtra = isAddonActive || mobileCfg.showExtraButtons;

        const labels = {
            generate: (isAddonActive && !manualData) ? "Generate AI Hints" : "Regenerate",
            hints: useEmojis ? "💡" : "Show Hints",
            options: useEmojis ? "🎯" : "Show Options",
            refresh: useEmojis ? "🔄" : "Refresh",
            json: useEmojis ? "📝" : "JSON",
            clear: useEmojis ? "🗑️" : "Clear",
            hideHints: useEmojis ? "💡" : "Hide Hints",
            hideOptions: useEmojis ? "🎯" : "Hide Options"
        };

        if (!document.getElementById('ai-hints-unified-styles')) {
            const s = document.createElement('style');
            s.id = 'ai-hints-unified-styles';
            s.textContent = STYLES;
            document.head.appendChild(s);
        }

        const ord = getCardOrd();
        const cardId = window.aiHintsCurrentCard ? window.aiHintsCurrentCard.id : 'temp';
        const stateKey = 'state_' + cardId + '_' + ord;
        const persistence = getPersistence();
        const isFirstLoad = !persistence.get(stateKey);
        let state = persistence.get(stateKey) || { hints: false, options: false, seed: Date.now() };

        // Auto-reveal logic based on configuration and actions
        if (isManualAction === true) {
            // Manual generation finished
            if (uiCfg.manual_show_hints) state.hints = true;
            if (uiCfg.manual_show_options) state.options = true;
            persistence.save(stateKey, state);
        } else if (isManualAction === false) {
            // Auto generation finished
            if (uiCfg.auto_show_hints) state.hints = true;
            if (uiCfg.auto_show_options) state.options = true;
            persistence.save(stateKey, state);
        } else if (isFirstLoad) {
            // Page load. If it's the first time seeing this card this session, apply the "On Card Load" config.
            if (uiCfg.auto_show_hints) state.hints = true;
            if (uiCfg.auto_show_options) state.options = true;
            persistence.save(stateKey, state);
        }

        const cardKey = 'c' + (ord + 1);
        const onAnswer = isAnswerSide();

        // Process existing blocks or create container
        let targetBlocks = manualData ? [null] : Array.from(jsonBlocks).filter(block => {
            try {
                const blockData = JSON.parse(block.textContent);
                if (blockBelongsToCurrentCard(block, blockData, cardKey, cardId, ord)) return true;
            } catch (e) {}
            block.remove();
            return false;
        });
        if (targetBlocks.length === 0 && isAddonActive) targetBlocks = [null];

        targetBlocks.forEach(block => {
            if (block && block.dataset.aiHintsRendered) return;
            try {
                let data = manualData;
                if (!data && block) {
                    data = JSON.parse(block.textContent);
                    if (data[cardKey]) data = data[cardKey];
                }
                
                const hasContent = data && (data.hints || data.options);
                const container = document.createElement('div');
                container.className = 'ai-hints-container';
                
                const btnBox = document.createElement('div');
                btnBox.className = 'ai-hints-btn-box';
                container.appendChild(btnBox);

                // Desktop: Generate Button
                if (isAddonActive) {
                    const genBtn = document.createElement('button');
                    genBtn.className = 'ai-hints-btn';
                    genBtn.textContent = hasContent ? "Regenerate" : "Generate AI Hints";
                    if (uiCfg.is_generating) {
                        genBtn.textContent = "✨ Generating...";
                        genBtn.disabled = true;
                        genBtn.classList.add('ai-hints-btn-generating');
                    }
                    genBtn.onclick = () => {
                        genBtn.disabled = true;
                        genBtn.textContent = "✨ Generating...";
                        if (typeof pycmd === 'function') pycmd('ai_hints_generate');
                    };
                    btnBox.appendChild(genBtn);
                }

                let hList, oList;
                if (hasContent) {
                    hList = renderSection(container, "AI Hints:", data.hints);
                    oList = renderSection(container, "AI Options:", data.options, (txt) => 
                        onAnswer && data.correct_answer && txt.trim().toLowerCase() === data.correct_answer.trim().toLowerCase(),
                        state.seed
                    );

                    if (hList) {
                        const btn = document.createElement('button');
                        btn.className = 'ai-hints-btn';
                        btn.textContent = state.hints ? labels.hideHints : labels.hints;
                        hList.style.display = state.hints ? 'block' : 'none';
                        if (state.hints) renderMath(hList);
                        btn.onclick = () => {
                            state.hints = hList.style.display !== 'block';
                            hList.style.display = state.hints ? 'block' : 'none';
                            btn.textContent = state.hints ? labels.hideHints : labels.hints;
                            if (state.hints) renderMath(hList);
                            persistence.save(stateKey, state);
                        };
                        btnBox.appendChild(btn);
                    }

                    if (oList) {
                        const btn = document.createElement('button');
                        btn.className = 'ai-hints-btn';
                        btn.textContent = state.options ? labels.hideOptions : labels.options;
                        oList.style.display = state.options ? 'block' : 'none';
                        if (state.options) renderMath(oList);
                        btn.onclick = () => {
                            state.options = oList.style.display !== 'block';
                            oList.style.display = state.options ? 'block' : 'none';
                            btn.textContent = state.options ? labels.hideOptions : labels.options;
                            if (state.options) renderMath(oList);
                            persistence.save(stateKey, state);
                        };
                        btnBox.appendChild(btn);
                    }

                    if (isAddonActive) {
                        const clrBtn = document.createElement('button');
                        clrBtn.className = 'ai-hints-btn';
                        clrBtn.textContent = labels.clear;
                        clrBtn.title = "Permanently clear hints from this card";
                        clrBtn.onclick = () => {
                            if (confirm("Permanently delete hints from this card?")) pycmd('ai_hints_clear');
                        };
                        btnBox.appendChild(clrBtn);
                    }

                    if (hasOverrideData) persistence.save(stateKey, state);
                }

                if (showExtra) {
                    const refBtn = document.createElement('button');
                    refBtn.className = 'ai-hints-btn';
                    refBtn.textContent = labels.refresh;
                    refBtn.onclick = () => {
                        if (isAddonActive) {
                            if (typeof pycmd === 'function') pycmd('ai_hints_refresh');
                        } else {
                            container.remove();
                            if (block) delete block.dataset.aiHintsRendered;
                            state.seed = Date.now();
                            persistence.save(stateKey, state);
                            init();
                        }
                    };
                    btnBox.appendChild(refBtn);

                    const jsonBtn = document.createElement('button');
                    jsonBtn.className = 'ai-hints-btn';
                    jsonBtn.textContent = labels.json;
                    jsonBtn.onclick = () => {
                        let view = container.querySelector('.ai-hints-json-view');
                        if (view) view.remove();
                        else {
                            view = document.createElement('pre');
                            view.className = 'ai-hints-json-view';
                            view.textContent = JSON.stringify(data, null, 2);
                            container.appendChild(view);
                        }
                    };
                    btnBox.appendChild(jsonBtn);
                }

                // Inject into page
                const qa = document.getElementById('qa');
                const target = document.querySelector('ai-hints') || (block ? block.nextSibling : qa ? qa.lastChild : null);
                if (target && target.tagName === 'AI-HINTS') {
                    target.innerHTML = '';
                    target.appendChild(container);
                } else if (block && block.parentNode) {
                    block.parentNode.insertBefore(container, block.nextSibling);
                } else if (qa) {
                    qa.appendChild(container);
                }

                if (block) block.dataset.aiHintsRendered = "true";
                if (onAnswer && hasContent) {
                    renderMath(container);
                }

            } catch (e) { console.error("AI-Hints Error:", e); }
        });
    }

    // API for Python
    window.aiHintsUpdateData = (data, isManualAction) => {
        if (window.aiHintsUiConfig) window.aiHintsUiConfig.is_generating = false;
        init(data, isManualAction);
    };
    window.aiHintsClearData = () => { 
        window.aiHintsLastSetupKey = undefined;
        document.querySelectorAll('.ai-hints-container').forEach(e => e.remove());
        document.querySelectorAll('.ai-hints-json').forEach(e => e.remove());
        
        // Clear state for this specific card
        const ord = getCardOrd();
        const cardId = window.aiHintsCurrentCard ? window.aiHintsCurrentCard.id : 'temp';
        const stateKey = 'state_' + cardId + '_' + ord;
        try { sessionStorage.removeItem('ai_hints_' + stateKey); } catch(e){}
        
        init(); 
    };
    window.aiHintsSetGenerating = (active, status, errorMsg) => {
        if (window.aiHintsUiConfig) window.aiHintsUiConfig.is_generating = !!active;
        let genBtns = document.querySelectorAll('.ai-hints-btn');
        if (active && genBtns.length === 0) {
            init();
            genBtns = document.querySelectorAll('.ai-hints-btn');
        }
        genBtns.forEach(btn => {
            if (btn.textContent.includes("AI Hints") || btn.textContent.includes("Regenerate") || btn.classList.contains('ai-hints-btn-generating')) {
                if (active) {
                    btn.disabled = true;
                    btn.textContent = "✨ Generating...";
                    btn.classList.add('ai-hints-btn-generating');
                } else {
                    btn.disabled = false;
                    btn.classList.remove('ai-hints-btn-generating');
                    if (status === 'Failed' || status === 'Offline') {
                        const oldTxt = btn.textContent;
                        btn.textContent = "❌ " + (status || "Failed");
                        if (errorMsg) btn.title = errorMsg;
                        setTimeout(() => { btn.textContent = oldTxt; btn.title = ""; }, 3000);
                    } else {
                        // Success or normal reset; init() will handle re-rendering labels
                        init();
                    }
                }
            }
        });
    };
    window.aiHintsSetup = (card, hints) => { 
        const setupKey = JSON.stringify({ card: card || null, hints: hints || null });
        
        // We only return early if we've already set up THIS exact data AND we know the container has content.
        // We cannot blindly return if ANY container exists, because a page reload might have
        // spawned an empty container (e.g. cached back-side HTML missing recently generated JSON).
        const existingContainer = document.querySelector('.ai-hints-container');
        const hasData = hints != null || document.querySelector('.ai-hints-json');
        const isEmptyContainer = existingContainer && !existingContainer.querySelector('.ai-hints-list') && !existingContainer.querySelector('.ai-hints-hint-list');
        
        if (window.aiHintsLastSetupKey === setupKey && existingContainer && (!hasData || !isEmptyContainer)) {
            return;
        }

        window.aiHintsLastSetupKey = setupKey;
        window.aiHintsCurrentCard = card; 
        
        if (existingContainer) {
            document.querySelectorAll('.ai-hints-container').forEach(e => e.remove());
        }
        
        // Never remove valid JSON blocks from the DOM here. clearData() handles stale JSON cleanup.
        document.querySelectorAll('.ai-hints-json').forEach(e => delete e.dataset.aiHintsRendered);
        
        init(hints); 
    };

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => init());
    else init();
    
    // AnkiDroid/Async handling
    if (!isAddonActive) setInterval(() => init(), 1000);
})();
