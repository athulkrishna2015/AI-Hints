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
        .ai-hints-container { margin-top: 10px; text-align: left; font-family: sans-serif; clear: both; }
        .ai-hints-content-box { margin-top: 8px; padding: 8px; border-radius: 8px; display: none; }
        .ai-hints-content-active { display: block; border: 1px dashed #aaa; background-color: rgba(128,128,128,0.06); }
        .ai-hints-btn-box { display: flex; flex-wrap: wrap; gap: 6px; justify-content: center; }
        .ai-hints-btn { padding: 4px 10px; cursor: pointer; border-radius: 6px; border: 1px solid #999; background-color: #f0f0f0; color: #222; font-size: 12px; font-weight: 500; transition: background 0.2s; -webkit-tap-highlight-color: transparent; }
        .ai-hints-btn:hover { background-color: #e0e0e0; }
        .ai-hints-btn:active { background-color: #d0d0d0; transform: translateY(1px); }
        .ai-hints-btn:disabled { opacity: 0.5; cursor: default; }
        .ai-hints-list, .ai-hints-hint-list { margin-top: 6px; padding-left: 20px; margin-bottom: 0; }
        .ai-hints-list li, .ai-hints-hint-list li { margin-bottom: 4px; line-height: 1.3; font-size: 13px; }
        .ai-hints-correct { border-left: 3px solid #2ecc71; background-color: rgba(46, 204, 113, 0.12); padding-left: 8px; font-weight: 600; border-radius: 0 4px 4px 0; }
        .nightMode .ai-hints-content-active { background-color: rgba(255,255,255,0.04); border-color: #555; }
        .nightMode .ai-hints-btn { background-color: #333; color: #eee; border-color: #666; }
        .nightMode .ai-hints-btn:hover { background-color: #444; }
        .ai-hints-title { font-weight: bold; margin-bottom: 2px; display: block; font-size: 11px; opacity: 0.7; text-transform: uppercase; letter-spacing: 0.5px; }
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
        if (isAddonActive && window.aiHintsCurrentCard && window.aiHintsCurrentCard.ord !== undefined && window.aiHintsCurrentCard.ord !== null) {
            return window.aiHintsCurrentCard.ord;
        }
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

    function renderSection(parent, title, items, isCorrectFn, seed, showTitle) {
        if (!items || items.length === 0) return null;
        
        const section = document.createElement('div');
        section.className = 'ai-hints-section';
        section.style.display = 'none';

        if (showTitle) {
            const label = document.createElement('span');
            label.className = 'ai-hints-title';
            label.textContent = title;
            section.appendChild(label);
        }

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
        section.appendChild(list);
        parent.appendChild(section);
        return section;
    }

    function blockBelongsToCurrentCard(block, data, cardKey, cardId, ord) {
        if (!block || !isAddonActive) return true;
        if (!window.aiHintsCurrentCard || cardId === 'temp') return true;

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
        
        // COMPATIBILITY: Don't re-render if user is currently editing a field 
        // (Edit Field During Review Native compatibility)
        if (!hasOverrideData && document.activeElement && (
            document.activeElement.isContentEditable || 
            document.activeElement.tagName === 'INPUT' || 
            document.activeElement.tagName === 'TEXTAREA'
        )) {
            return;
        }

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
            if (uiCfg.manual_show_hints) state.hints = true;
            if (uiCfg.manual_show_options) state.options = true;
            persistence.save(stateKey, state);
        } else if (isManualAction === false) {
            if (uiCfg.auto_show_hints) state.hints = true;
            if (uiCfg.auto_show_options) state.options = true;
            persistence.save(stateKey, state);
        } else if (isFirstLoad) {
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

                const contentBox = document.createElement('div');
                contentBox.className = 'ai-hints-content-box';
                container.appendChild(contentBox);

                const showTitles = data && data.hints && data.hints.length > 0 && data.options && data.options.length > 0;

                const hSection = renderSection(contentBox, "Hints:", (data ? data.hints : []), null, 0, showTitles);
                const oSection = renderSection(contentBox, "Options:", (data ? data.options : []), (txt) => 
                    onAnswer && data.correct_answer && txt.trim().toLowerCase() === data.correct_answer.trim().toLowerCase(),
                    state.seed, showTitles
                );

                const updateVisibility = () => {
                    const anyVisible = state.hints || state.options;
                    contentBox.className = anyVisible ? 'ai-hints-content-box ai-hints-content-active' : 'ai-hints-content-box';
                    if (hSection) hSection.style.display = state.hints ? 'block' : 'none';
                    if (oSection) oSection.style.display = state.options ? 'block' : 'none';
                };

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

                if (hasContent) {
                    if (hSection) {
                        const btn = document.createElement('button');
                        btn.className = 'ai-hints-btn';
                        btn.textContent = state.hints ? labels.hideHints : labels.hints;
                        btn.onclick = () => {
                            state.hints = !state.hints;
                            btn.textContent = state.hints ? labels.hideHints : labels.hints;
                            updateVisibility();
                            if (state.hints) renderMath(hSection);
                            persistence.save(stateKey, state);
                        };
                        btnBox.appendChild(btn);
                    }

                    if (oSection) {
                        const btn = document.createElement('button');
                        btn.className = 'ai-hints-btn';
                        btn.textContent = state.options ? labels.hideOptions : labels.options;
                        btn.onclick = () => {
                            state.options = !state.options;
                            btn.textContent = state.options ? labels.hideOptions : labels.options;
                            updateVisibility();
                            if (state.options) renderMath(oSection);
                            persistence.save(stateKey, state);
                        };
                        btnBox.appendChild(btn);
                    }

                    // Clear button (Default on all platforms)
                    const clrBtn = document.createElement('button');
                    clrBtn.className = 'ai-hints-btn';
                    clrBtn.textContent = labels.clear;
                    clrBtn.title = isAddonActive ? "Permanently clear hints from this card" : "Hide hints for this session";
                    clrBtn.onclick = () => {
                        if (isAddonActive) {
                            if (confirm("Permanently delete hints from this card?")) pycmd('ai_hints_clear');
                        } else {
                            window.aiHintsClearData();
                        }
                    };
                    btnBox.appendChild(clrBtn);
                    
                    updateVisibility();
                    if (state.hints && hSection) renderMath(hSection);
                    if (state.options && oSection) renderMath(oSection);
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
        window.aiHintsSetupToken = undefined;
        document.querySelectorAll('.ai-hints-container').forEach(e => e.remove());
        document.querySelectorAll('.ai-hints-json').forEach(e => e.remove());
        
        // Clear all state keys for this specific card to prevent ghost reveals
        const ord = getCardOrd();
        const cardId = window.aiHintsCurrentCard ? window.aiHintsCurrentCard.id : 'temp';
        const prefix = 'state_' + cardId + '_' + ord;
        
        try {
            sessionStorage.removeItem('ai_hints_' + prefix);
            for (let i = 0; i < sessionStorage.length; i++) {
                const key = sessionStorage.key(i);
                if (key && (key.includes(cardId) || key.startsWith('ai_hints_state'))) {
                    sessionStorage.removeItem(key);
                    i--;
                }
            }
        } catch(e){}
        
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
                        init();
                    }
                }
            }
        });
    };
    window.aiHintsSetup = (card, hints) => { 
        const setupKey = JSON.stringify({ card: card || null, hints: hints || null });
        const currentAnswerState = isAnswerSide();
        const existingContainer = document.querySelector('.ai-hints-container');
        const hasData = hints != null || document.querySelector('.ai-hints-json');
        const isEmptyContainer = existingContainer && !existingContainer.querySelector('.ai-hints-list') && !existingContainer.querySelector('.ai-hints-hint-list');
        
        if (window.aiHintsLastSetupKey === setupKey && existingContainer && (!hasData || !isEmptyContainer) && window.aiHintsLastAnswerState === currentAnswerState) {
            return;
        }

        window.aiHintsLastSetupKey = setupKey;
        window.aiHintsLastAnswerState = currentAnswerState;
        window.aiHintsCurrentCard = card; 
        
        if (existingContainer) {
            document.querySelectorAll('.ai-hints-container').forEach(e => e.remove());
        }
        document.querySelectorAll('.ai-hints-json').forEach(e => delete e.dataset.aiHintsRendered);
        init(hints); 
    };

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => init());
    else init();
    
    if (!isAddonActive) setInterval(() => init(), 1000);
})();
