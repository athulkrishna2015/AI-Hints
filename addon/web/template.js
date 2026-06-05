/**
 * AI-Hints Unified Template Script
 * This script handles AI Hints rendering for ALL platforms (Desktop, AnkiDroid, AnkiMobile, Web).
 * 
 * If Python (addon) is detected, it enables full control (Generate, Clear, etc.).
 * Otherwise, it provides a standalone viewer for mobile.
 */
(function() {
    // Track loaded status for diagnostics
    window.aiHintsUnifiedLoaded = true;

    // 1. Configuration & Styling
    const STYLES = `
        .ai-hints-container { margin-top: 10px; text-align: left; font-family: sans-serif; clear: both; font-size: inherit; }
        .ai-hints-content-box { margin-top: 8px; padding: 8px; border-radius: 8px; display: none; }
        .ai-hints-content-active { display: block; border: 1px dashed #aaa; background-color: rgba(128,128,128,0.06); }
        .ai-hints-btn-box { display: flex; flex-wrap: wrap; gap: 6px; justify-content: center; }
        .ai-hints-btn { padding: 4px 10px; cursor: pointer; border-radius: 6px; border: 1px solid #999; background-color: #f0f0f0; color: #222; font-size: 12px; font-weight: 500; transition: background-color 0.15s ease, box-shadow 0.15s ease; -webkit-tap-highlight-color: transparent; user-select: none; -webkit-user-select: none; }
        .ai-hints-btn:hover { background-color: #e0e0e0; }
        .ai-hints-btn:active { background-color: #d0d0d0; transform: translateY(1px); }
        .ai-hints-btn:disabled { opacity: 0.5; cursor: default; }
        .ai-hints-list, .ai-hints-hint-list { margin-top: 6px; padding-left: 20px; margin-bottom: 0; }
        .ai-hints-list li, .ai-hints-hint-list li { margin-bottom: 4px; line-height: 1.3; }
        .ai-hints-correct { border-left: 3px solid #2ecc71; background-color: rgba(46, 204, 113, 0.12); padding-left: 8px; font-weight: 600; border-radius: 0 4px 4px 0; }
        .nightMode .ai-hints-content-active { background-color: rgba(255,255,255,0.04); border-color: #555; }
        .nightMode .ai-hints-btn { background-color: #333; color: #eee; border-color: #666; }
        .nightMode .ai-hints-btn:hover { background-color: #444; }
        .ai-hints-title { font-weight: bold; margin-bottom: 2px; display: block; font-size: 11px; opacity: 0.7; text-transform: uppercase; letter-spacing: 0.5px; }
        .ai-hints-json-view { margin-top: 10px; padding: 8px; background: rgba(0,0,0,0.05); border-radius: 5px; font-family: monospace; font-size: 11px; white-space: pre-wrap; overflow-x: auto; }
        .nightMode .ai-hints-json-view { background: rgba(255,255,255,0.05); }
        .ai-hints-btn-generating { animation: ai-hints-pulse 1.5s ease-in-out infinite; background: linear-gradient(90deg, #f8fafc 0%, #dbeafe 50%, #f8fafc 100%); background-size: 200% 100%; color: #111827; border-color: #60a5fa; will-change: background-position; }
        .nightMode .ai-hints-btn-generating { background: linear-gradient(90deg, #172554 0%, #1d4ed8 50%, #172554 100%); background-size: 200% 100%; color: #ffffff; border-color: #93c5fd; will-change: background-position; }
        .ai-hints-btn-pregenerating { animation: ai-hints-pregen-pulse 2s ease-in-out infinite; background: linear-gradient(90deg, #f0fdf4 0%, #dcfce7 50%, #f0fdf4 100%); background-size: 200% 100%; border-color: #86efac; will-change: background-position; }
        .nightMode .ai-hints-btn-pregenerating { background: linear-gradient(90deg, #064e3b 0%, #166534 50%, #064e3b 100%); background-size: 200% 100%; border-color: #22c55e; }
        @keyframes ai-hints-pulse { 0% { background-position: 100% 0; } 100% { background-position: -100% 0; } }
        @keyframes ai-hints-pregen-pulse { 0% { background-position: 100% 0; } 100% { background-position: -100% 0; } }
    `;

    // 2. State & Helpers
    const isAddonActive = !!window.aiHintsUiConfig;

    function hashCode(str) {
        let hash = 0;
        for (let i = 0; i < str.length; i++) {
            const char = str.charCodeAt(i);
            hash = ((hash << 5) - hash) + char;
            hash |= 0;
        }
        return Math.abs(hash).toString(36);
    }
    
    function getPersistence() {
        return {
            save: (key, val) => { try { sessionStorage.setItem('ai_hints_' + key, JSON.stringify(val)); } catch(e){} },
            get: (key) => { try { return JSON.parse(sessionStorage.getItem('ai_hints_' + key)); } catch(e){ return null; } }
        };
    }

    function isAnswerSide() {
        // 1. Check cloze blanks (for Cloze cards on mobile/desktop without Python)
        const clozes = document.querySelectorAll('.cloze');
        if (clozes.length > 0) {
            let hasBlank = false;
            for (let i = 0; i < clozes.length; i++) {
                const txt = clozes[i].textContent.trim();
                if (txt.includes('[...]') || (txt.startsWith('[') && txt.endsWith(']'))) {
                    hasBlank = true;
                    break;
                }
            }
            if (!hasBlank) return true;
        }

        // 2. Standard template fallback
        return !!document.getElementById('answer') || !!document.querySelector('.answer') || !!document.querySelector('#answer') || document.body.classList.contains('answer') || (window.aiHintsUiConfig && window.aiHintsUiConfig.is_answer_side);
    }

    function getCardOrd() {
        // If Python backend is active, use the exact ordinal passed by Anki Desktop.
        if (isAddonActive && window.aiHintsCurrentCard && window.aiHintsCurrentCard.ord !== undefined && window.aiHintsCurrentCard.ord !== null) {
            return window.aiHintsCurrentCard.ord;
        }

        // CRITICAL FOR MOBILE Sync (AnkiDroid, AnkiMobile, Web Reviewer):
        // When Python is not running, we must dynamically detect which cloze deletion is active.
        // 1. Try body class name: Anki and AnkiDroid set classes like 'card1' (for c1), 'card2' (for c2),
        //    etc., directly on the <body> tag. This is the most reliable way to find the current cloze.
        const bodyClass = document.body.className;
        const bodyMatch = bodyClass.match(/\bcard(\d+)\b/);
        if (bodyMatch) {
            return parseInt(bodyMatch[1]) - 1;
        }

        // 2. Fallback to active cloze class: Some custom templates might tag clozes with classes like 'c1', 'c2'.
        //    Note: Standard Anki/AnkiDroid only uses class='cloze' without numbering, so this is just a backup.
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

    // Helper to ensure mathematical formulas are parsed correctly by Anki's MathJax engine.
    // If standard LaTeX delimiters are already present (like \(...\) in hints), we leave the text as-is.
    // If the text is bare math/LaTeX (contains math operators but no delimiters), we wrap it in inline \( and \) tags.
    function convertMathDelimitersToTags(text) {
        if (!text) return "";
        let processed = text.trim();
        
        // Return immediately if standard math delimiters are already present
        let hasDelimiters = /\\\(|\\\[|\$\$|\$/.test(processed);
        if (hasDelimiters) {
            return processed;
        }

        // Auto-wrap bare LaTeX math in inline delimiters \( ... \) so MathJax recognizes it
        const mathIndicators = /\\[A-Za-z]+|[\^\_]\{|\\int|\\sqrt|\\frac|\\sin|\\cos|\\omega|\\pi|\\lambda|\\theta|\\alpha|\\beta|\\gamma|\\delta|\\partial/;
        if (mathIndicators.test(processed)) {
            return '\\(' + processed + '\\)';
        }

        return processed;
    }

    function renderSection(parent, title, items, isCorrectFn, seed, showTitle, correctIndex) {
        if (!items || items.length === 0) return null;
        
        const section = document.createElement('div');
        // Add 'tex2jax_process' to bypass Anki's global 'tex2jax_ignore' card wrapper
        section.className = 'ai-hints-section tex2jax_process';
        section.style.display = 'none';

        if (showTitle) {
            const label = document.createElement('span');
            label.className = 'ai-hints-title';
            label.textContent = title;
            section.appendChild(label);
        }

        const list = document.createElement('ul');
        list.className = title.toLowerCase().includes('hint') ? 'ai-hints-hint-list' : 'ai-hints-list';
        const listItems = items.map((text, index) => {
            const li = document.createElement('li');
            li.innerHTML = convertMathDelimitersToTags(text);
            if ((correctIndex !== undefined && correctIndex !== null && index === correctIndex) || (isCorrectFn && isCorrectFn(text))) {
                li.className = 'ai-hints-correct';
            }
            return li;
        });
        if (title.toLowerCase().includes('option')) shuffle(listItems, seed);
        listItems.forEach(li => list.appendChild(li));
        section.appendChild(list);
        parent.appendChild(section);
        return section;
    }

    function decodeHtmlEntities(text) {
        const raw = (text || "").toString();
        if (typeof document !== 'undefined' && document.createElement) {
            try {
                const textarea = document.createElement('textarea');
                textarea.innerHTML = raw;
                if (textarea.value) return textarea.value;
            } catch (e) {}
        }
        return raw
            .replace(/&nbsp;/gi, ' ')
            .replace(/&amp;/gi, '&')
            .replace(/&lt;/gi, '<')
            .replace(/&gt;/gi, '>')
            .replace(/&quot;/gi, '"')
            .replace(/&#39;/gi, "'")
            .replace(/&apos;/gi, "'");
    }

    function normalizeAnswerText(value) {
        let text = decodeHtmlEntities(value)
            .replace(/<br\s*\/?>/gi, ' ')
            .replace(/<\/?(?:anki-mathjax|mjx-container|span|div|p|b|strong|em|i)[^>]*>/gi, ' ')
            .replace(/<[^>]*>/g, ' ')
            .replace(/\u00a0/g, ' ')
            .replace(/[“”]/g, '"')
            .replace(/[‘’]/g, "'")
            .replace(/[−–—]/g, '-')
            .trim()
            .toLowerCase();

        text = text.replace(/^(?:answer|option|choice)\s*[:.)-]\s*/i, '');

        let changed = true;
        while (changed) {
            changed = false;
            const before = text;
            text = text
                .replace(/^\\\(([\s\S]*)\\\)$/g, '$1')
                .replace(/^\\\[([\s\S]*)\\\]$/g, '$1')
                .replace(/^\${1,2}([\s\S]*)\${1,2}$/g, '$1')
                .replace(/^<anki-mathjax>([\s\S]*)<\/anki-mathjax>$/i, '$1')
                .trim();
            changed = text !== before;
        }

        return text
            .replace(/\\displaystyle\b/g, '')
            .replace(/\s+/g, ' ')
            .trim();
    }

    function answersMatch(optionText, correctAnswer) {
        const option = normalizeAnswerText(optionText);
        const correct = normalizeAnswerText(correctAnswer);
        if (!option || !correct) return false;
        if (option === correct) return true;

        const compact = (s) => s.replace(/\s+/g, '');
        return compact(option) === compact(correct);
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
        if (!blockCardId && !isKeyed && String(ord) !== '0') return false;

        return true;
    }

    function clearRenderedContainers() {
        const selector = isAddonActive ? '.ai-hints-container' : '.ai-hints-container-rendered';
        document.querySelectorAll(selector).forEach(e => e.remove());
    }

    function resetJsonRenderMarkers() {
        document.querySelectorAll('.ai-hints-json').forEach(e => delete e.dataset.aiHintsRendered);
    }

    function pruneForeignJsonBlocks(cardId, ord) {
        if (!isAddonActive || !window.aiHintsCurrentCard || cardId === 'temp') return;
        document.querySelectorAll('.ai-hints-json').forEach(block => {
            const blockCardId = block.getAttribute ? block.getAttribute('data-ai-hints-card-id') : null;
            const blockOrd = block.getAttribute ? block.getAttribute('data-ai-hints-card-ord') : null;
            const idMismatch = blockCardId && String(blockCardId) !== String(cardId);
            const ordMismatch = blockOrd !== null && blockOrd !== undefined && blockOrd !== '' && String(blockOrd) !== String(ord);
            if (idMismatch || ordMismatch) block.remove();
        });
    }

    function retryInitForCard(cardId, ord) {
        if (!isAddonActive) return false;
        const key = String(cardId) + '_' + String(ord);
        window.aiHintsRetryState = window.aiHintsRetryState || {};
        const attempts = window.aiHintsRetryState[key] || 0;
        if (attempts >= 8) return false;
        window.aiHintsRetryState[key] = attempts + 1;
        setTimeout(() => {
            const currentId = window.aiHintsCurrentCard ? window.aiHintsCurrentCard.id : 'temp';
            const currentOrd = getCardOrd();
            if (String(currentId) === String(cardId) && String(currentOrd) === String(ord)) {
                init();
            }
        }, 75);
        return true;
    }

    // 3. Main Init
    function init(manualData, isManualAction) {
        // manualData presence indicates an update from Python after generation
        const hasOverrideData = !!manualData;
        
        // COMPATIBILITY: Don't re-render if user is currently editing a field 
        if (!hasOverrideData && document.activeElement && (
            document.activeElement.isContentEditable || 
            document.activeElement.tagName === 'INPUT' || 
            document.activeElement.tagName === 'TEXTAREA'
        )) {
            return;
        }

        const ord = getCardOrd();
        let cardId = window.aiHintsCurrentCard ? window.aiHintsCurrentCard.id : 'temp';
        if (cardId === 'temp') {
            const firstJson = document.querySelector('.ai-hints-json');
            if (firstJson) {
                cardId = 'h' + hashCode(firstJson.textContent);
            } else {
                const qa = document.getElementById('qa') || document.body;
                cardId = 'h' + hashCode(qa.innerText || qa.textContent || '');
            }
        }
        const cardKey = 'c' + (ord + 1);
        const onAnswer = isAnswerSide();

        // Check if we already have a container rendered for this card and state
        // to avoid unnecessary clearing which causes flicker.
        const existingContainer = document.querySelector('.ai-hints-container-rendered');
        const sameCard = existingContainer && 
                        existingContainer.getAttribute('data-ai-hints-card-id') === String(cardId) &&
                        existingContainer.getAttribute('data-ai-hints-card-ord') === String(ord);
        
        // If we are already rendered and this is not a manual override, we might be able to bail early
        if (!hasOverrideData && sameCard && window.aiHintsLastAnswerState === onAnswer) {
            // Further check: do we have new JSON blocks that need rendering?
            const unrenderedBlocks = Array.from(document.querySelectorAll('.ai-hints-json')).filter(block => {
                try {
                    if (block.dataset.aiHintsRendered) return false;
                    const blockData = JSON.parse(block.textContent);
                    return blockBelongsToCurrentCard(block, blockData, cardKey, cardId, ord);
                } catch (e) { return false; }
            });
            
            if (unrenderedBlocks.length === 0) {
                // Already rendered for this card/state and no new data blocks found.
                return;
            }
        }

        // Remove every visible hints container before scanning data so stale buttons cannot flash or be scraped.
        clearRenderedContainers();

        resetJsonRenderMarkers();
        pruneForeignJsonBlocks(cardId, ord);

        const jsonBlocks = document.querySelectorAll('.ai-hints-json');
        const containers = document.querySelectorAll('.ai-hints-container');
        
        // Configuration
        const uiCfg = window.aiHintsUiConfig || {};
        const mobileCfg = window.aiHintsMobileConfig || {};

        // If no data blocks and no containers, and not in active addon mode, we still need to potentially 
        // show the "Generate" button if that's enabled, or check for HTML containers.
        if (jsonBlocks.length === 0 && containers.length === 0 && !hasOverrideData && !isAddonActive && !mobileCfg.showExtraButtons) {
            // Ensure any static containers are hidden if we are not rendering the interactive UI
            containers.forEach(c => c.style.display = 'none');
            return;
        }

        // Always hide original static containers from the page when rendering the interactive UI
        containers.forEach(c => {
            if (!c.classList.contains('ai-hints-container-rendered')) {
                c.style.display = 'none';
            }
        });

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
            let finalStyles = STYLES;
            if (uiCfg && uiCfg.hints_font_size) {
                finalStyles += `\n.ai-hints-container { font-size: ${uiCfg.hints_font_size} !important; }`;
            }
            s.textContent = finalStyles;
            document.head.appendChild(s);
        }

        const stateKey = 'state_' + cardId + '_' + ord;
        const persistence = getPersistence();
        const doNotCollapse = !!uiCfg.do_not_auto_collapse || (mobileCfg && !!mobileCfg.doNotAutoCollapse);

        let state;
        if (doNotCollapse) {
            const globalState = persistence.get('global_state') || { hints: !!uiCfg.auto_show_hints, options: !!uiCfg.auto_show_options };
            state = persistence.get(stateKey) || { hints: globalState.hints, options: globalState.options, seed: Math.floor(Math.random() * 1000000), cleared: false, showJson: false };
            state.hints = globalState.hints;
            state.options = globalState.options;
            if (!onAnswer) {
                state.seed = Math.floor(Math.random() * 1000000);
                persistence.save(stateKey, state);
            }
        } else {
            state = persistence.get(stateKey) || { hints: false, options: false, seed: Math.floor(Math.random() * 1000000), cleared: false, showJson: false };
            if (!onAnswer) {
                state.hints = !!uiCfg.auto_show_hints;
                state.options = !!uiCfg.auto_show_options;
                state.seed = Math.floor(Math.random() * 1000000);
                persistence.save(stateKey, state);
            }
        }

        const isFirstLoad = !persistence.get(stateKey);

        if (state.cleared && !isAddonActive) {
            // If cleared in this session, ensure static boxes remain hidden and return
            containers.forEach(c => c.style.display = 'none');
            return;
        }

        // Auto-reveal logic
        if (isManualAction === true) {
            if (uiCfg.manual_show_hints) state.hints = true;
            if (uiCfg.manual_show_options) state.options = true;
            persistence.save(stateKey, state);
            if (doNotCollapse) {
                persistence.save('global_state', { hints: state.hints, options: state.options });
            }
        } else if (isManualAction === false) {
            if (uiCfg.auto_show_hints) state.hints = true;
            if (uiCfg.auto_show_options) state.options = true;
            persistence.save(stateKey, state);
            if (doNotCollapse) {
                persistence.save('global_state', { hints: state.hints, options: state.options });
            }
        } else if (isFirstLoad) {
            if (!doNotCollapse) {
                if (uiCfg.auto_show_hints) state.hints = true;
                if (uiCfg.auto_show_options) state.options = true;
                persistence.save(stateKey, state);
            }
        }

        // Unconditional display on the back/answer side regardless of other settings
        if (onAnswer) {
            state.hints = true;
            state.options = true;
        }

        // Process existing blocks or containers
        let targetBlocks = manualData ? [null] : Array.from(jsonBlocks).filter(block => {
            try {
                const blockData = JSON.parse(block.textContent);
                if (blockBelongsToCurrentCard(block, blockData, cardKey, cardId, ord)) return true;
            } catch (e) {}
            return false;
        });

        // Mobile Fallback: If no JSON blocks were found but we have HTML containers, treat them as targets
        if (targetBlocks.length === 0 && !isAddonActive && containers.length > 0) {
            targetBlocks = Array.from(containers).filter(c => {
                // Skip if it's already one we rendered
                if (c.classList.contains('ai-hints-container-rendered')) return false;
                // Check if it belongs to this card (if it has the attributes)
                return blockBelongsToCurrentCard(c, null, cardKey, cardId, ord);
            });
        }

        if (targetBlocks.length === 0 && isAddonActive) {
            if (!hasOverrideData && jsonBlocks.length > 0) {
                if (retryInitForCard(cardId, ord)) return;
            }
            targetBlocks = [null];
        } else if (isAddonActive && targetBlocks.length > 1) targetBlocks = targetBlocks.slice(0, 1);

        // Ensure we clear the placeholder if we are about to render something (or even if we are not, if it was stale)
        const placeholder = document.querySelector('ai-hints');
        if (placeholder) placeholder.innerHTML = '';

        targetBlocks.forEach(block => {
            if (block && block.dataset.aiHintsRendered) return;
            try {
                let data = manualData;
                if (!data && block) {
                    if (block.classList.contains('ai-hints-json')) {
                        data = JSON.parse(block.textContent);
                        if (data[cardKey]) data = data[cardKey];
                    } else if (block.classList.contains('ai-hints-container')) {
                        // Scraping fallback for HTML-only containers
                        data = { hints: [], options: [] };
                        block.querySelectorAll('.ai-hints-hint-list li').forEach(li => data.hints.push(li.innerHTML));
                        block.querySelectorAll('.ai-hints-list li').forEach(li => data.options.push(li.innerHTML));
                        // Hide the original static block so we can replace it with our interactive one
                        block.style.display = 'none';
                    }
                }
                
                // Track this setup to prevent redundant calls from Python
                window.aiHintsLastSetupKey = JSON.stringify({ 
                    card: { id: String(cardId), ord: ord }, 
                    hints: data || null 
                });
                window.aiHintsLastAnswerState = onAnswer;

                const hasContent = data && (data.hints || data.options);
                const container = document.createElement('div');
                container.className = 'ai-hints-container ai-hints-container-rendered';
                container.setAttribute('contenteditable', 'false');
                container.setAttribute('data-ai-hints-card-id', String(cardId));
                if (ord !== undefined && ord !== null) container.setAttribute('data-ai-hints-card-ord', String(ord));
                
                const btnBox = document.createElement('div');
                btnBox.className = 'ai-hints-btn-box';
                container.appendChild(btnBox);

                const contentBox = document.createElement('div');
                contentBox.className = 'ai-hints-content-box';
                container.appendChild(contentBox);

                const showTitles = data && data.hints && data.hints.length > 0 && data.options && data.options.length > 0;
                const correctIndex = (
                    onAnswer &&
                    data &&
                    data.correct_answer &&
                    data.options &&
                    data.options.length > 0 &&
                    answersMatch(data.options[0], data.correct_answer)
                ) ? 0 : null;

                const hSection = renderSection(contentBox, "Hints:", (data ? data.hints : []), null, 0, showTitles);
                const oSection = renderSection(contentBox, "Options:", (data ? data.options : []), (txt) => 
                    onAnswer && data.correct_answer && answersMatch(txt, data.correct_answer),
                    state.seed, showTitles, correctIndex
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
                    } else if (uiCfg.is_pregenerating) {
                        // Background pre-gen active for another card
                        genBtn.classList.add('ai-hints-btn-pregenerating');
                        genBtn.title = "Background pre-generation active...";
                    }
                    
                    genBtn.onclick = (e) => {
                        if (e) { e.stopPropagation(); e.preventDefault(); }
                        genBtn.disabled = true;
                        genBtn.textContent = "✨ Generating...";
                        // Switch to foreground style immediately
                        genBtn.classList.remove('ai-hints-btn-pregenerating');
                        genBtn.classList.add('ai-hints-btn-generating');
                        if (typeof pycmd === 'function') pycmd('ai_hints_generate');
                    };
                    btnBox.appendChild(genBtn);
                }

                const saveState = () => {
                    persistence.save(stateKey, state);
                    if (doNotCollapse) {
                        persistence.save('global_state', { hints: state.hints, options: state.options });
                    }
                };

                if (hasContent) {
                    if (hSection) {
                        const btn = document.createElement('button');
                        btn.className = 'ai-hints-btn';
                        btn.textContent = state.hints ? labels.hideHints : labels.hints;
                        btn.onclick = (e) => {
                            if (e) { e.stopPropagation(); e.preventDefault(); }
                            state.hints = !state.hints;
                            btn.textContent = state.hints ? labels.hideHints : labels.hints;
                            updateVisibility();
                            if (state.hints) renderMath(hSection);
                            saveState();
                        };
                        btnBox.appendChild(btn);
                    }

                    if (oSection) {
                        const btn = document.createElement('button');
                        btn.className = 'ai-hints-btn';
                        btn.textContent = state.options ? labels.hideOptions : labels.options;
                        btn.onclick = (e) => {
                            if (e) { e.stopPropagation(); e.preventDefault(); }
                            state.options = !state.options;
                            btn.textContent = state.options ? labels.hideOptions : labels.options;
                            updateVisibility();
                            if (state.options) renderMath(oSection);
                            saveState();
                        };
                        btnBox.appendChild(btn);
                    }

                    // Clear button (Only available when Python addon is active)
                    if (isAddonActive) {
                        const clrBtn = document.createElement('button');
                        clrBtn.className = 'ai-hints-btn';
                        clrBtn.textContent = labels.clear;
                        clrBtn.title = "Permanently clear hints from this card";
                        clrBtn.onclick = (e) => {
                            if (e) { e.stopPropagation(); e.preventDefault(); }
                            if (confirm("Permanently delete hints from this card?")) pycmd('ai_hints_clear');
                        };
                        btnBox.appendChild(clrBtn);
                    }
                    
                    updateVisibility();
                    if (state.hints && hSection) renderMath(hSection);
                    if (state.options && oSection) renderMath(oSection);
                    if (hasOverrideData) saveState();
                }

                if (showExtra) {
                    const refBtn = document.createElement('button');
                    refBtn.className = 'ai-hints-btn';
                    refBtn.textContent = labels.refresh;
                    refBtn.onclick = (e) => {
                        if (e) { e.stopPropagation(); e.preventDefault(); }
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

                    if (state.showJson && data) {
                        const view = document.createElement('pre');
                        view.className = 'ai-hints-json-view';
                        view.textContent = JSON.stringify(data, null, 2);
                        container.appendChild(view);
                    }

                    const jsonBtn = document.createElement('button');
                    jsonBtn.className = 'ai-hints-btn';
                    jsonBtn.textContent = labels.json;
                    jsonBtn.onclick = (e) => {
                        if (e) { e.stopPropagation(); e.preventDefault(); }
                        let view = container.querySelector('.ai-hints-json-view');
                        if (view) {
                            view.remove();
                            state.showJson = false;
                        }
                        else {
                            view = document.createElement('pre');
                            view.className = 'ai-hints-json-view';
                            view.textContent = JSON.stringify(data, null, 2);
                            container.appendChild(view);
                            state.showJson = true;
                        }
                        saveState();
                    };
                    btnBox.appendChild(jsonBtn);
                }

                // Inject into page
                const qa = document.getElementById('qa');
                const target = document.querySelector('ai-hints');
                const displayPosition = uiCfg.answer_display_position || 'between';
                if (target && target.tagName === 'AI-HINTS') {
                    target.innerHTML = ''; // Ensure placeholder is clean
                    target.appendChild(container);
                } else if (onAnswer && displayPosition === 'bottom' && qa) {
                    // On answer side, if configured, append at the very bottom of the card
                    qa.appendChild(container);
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
        // Only clear the global is_generating flag if this update actually came from a card 
        // that belongs on the screen. Pre-generations should not touch the global flag.
        const ord = getCardOrd();
        const cardId = window.aiHintsCurrentCard ? window.aiHintsCurrentCard.id : 'temp';
        const dataCardId = (data && data._id) ? data._id : null;
        const dataCardOrd = (data && data._ord !== undefined) ? data._ord : null;

        const isCurrentCard = !dataCardId || (String(dataCardId) === String(cardId) && 
                              (dataCardOrd === null || String(dataCardOrd) === String(ord)));

        if (isCurrentCard && window.aiHintsUiConfig) {
            window.aiHintsUiConfig.is_generating = false;
        }
        init(data, isManualAction);
    };
    window.aiHintsClearData = () => { 
        window.aiHintsLastSetupKey = undefined;
        window.aiHintsSetupToken = undefined;
        
        // Clear all state keys for this specific card
        const ord = getCardOrd();
        let cardId = window.aiHintsCurrentCard ? window.aiHintsCurrentCard.id : 'temp';
        if (cardId === 'temp') {
            const firstJson = document.querySelector('.ai-hints-json');
            if (firstJson) {
                cardId = 'h' + hashCode(firstJson.textContent);
            } else {
                const qa = document.getElementById('qa') || document.body;
                cardId = 'h' + hashCode(qa.innerText || qa.textContent || '');
            }
        }
        const prefix = 'state_' + cardId + '_' + ord;
        const persistence = getPersistence();
        
        try {
            // On mobile, we set a 'cleared' flag to keep it hidden for this session
            if (!isAddonActive) {
                const state = persistence.get(prefix) || {};
                state.cleared = true;
                persistence.save(prefix, state);
            } else {
                sessionStorage.removeItem('ai_hints_' + prefix);
            }
        } catch(e){}
        
        document.querySelectorAll('.ai-hints-container').forEach(e => e.remove());
        document.querySelectorAll('.ai-hints-json').forEach(e => e.remove());
        
        init(); 
    };
    window.aiHintsSetGenerating = (active, status, errorMsg, cardId, isPregen) => {
        const currentCardId = window.aiHintsCurrentCard ? String(window.aiHintsCurrentCard.id) : 'temp';
        const strCardId = cardId ? String(cardId) : null;
        const isThisCard = strCardId === currentCardId;
        
        window.aiHintsBackgroundGenerations = window.aiHintsBackgroundGenerations || new Set();
        
        if (active) {
            if (isThisCard) {
                if (window.aiHintsUiConfig) window.aiHintsUiConfig.is_generating = true;
            } else if (strCardId) {
                window.aiHintsBackgroundGenerations.add(strCardId);
                if (window.aiHintsUiConfig) window.aiHintsUiConfig.is_pregenerating = true;
            }
        } else {
            if (isThisCard) {
                if (window.aiHintsUiConfig) window.aiHintsUiConfig.is_generating = false;
            }
            if (strCardId) window.aiHintsBackgroundGenerations.delete(strCardId);
            if (window.aiHintsUiConfig) {
                // Background animation only if we have active background tasks
                window.aiHintsUiConfig.is_pregenerating = (window.aiHintsBackgroundGenerations.size > 0);
            }
        }

        const uiCfg = window.aiHintsUiConfig || {};
        let genBtns = document.querySelectorAll('.ai-hints-btn');
        if (active && genBtns.length === 0) {
            init();
            genBtns = document.querySelectorAll('.ai-hints-btn');
        }
        
        genBtns.forEach(btn => {
            if (btn.textContent.includes("AI Hints") || btn.textContent.includes("Regenerate") || 
                btn.classList.contains('ai-hints-btn-generating') || btn.classList.contains('ai-hints-btn-pregenerating')) {
                
                if (uiCfg.is_generating) {
                    btn.disabled = true;
                    btn.textContent = "✨ Generating...";
                    btn.classList.remove('ai-hints-btn-pregenerating');
                    btn.classList.add('ai-hints-btn-generating');
                } else if (uiCfg.is_pregenerating) {
                    btn.disabled = false;
                    btn.classList.remove('ai-hints-btn-generating');
                    btn.classList.add('ai-hints-btn-pregenerating');
                } else {
                    btn.disabled = false;
                    btn.classList.remove('ai-hints-btn-generating');
                    btn.classList.remove('ai-hints-btn-pregenerating');
                    
                    if (isThisCard && (status === 'Failed' || status === 'Offline')) {
                        const oldTxt = btn.textContent;
                        btn.textContent = "❌ " + (status || "Failed");
                        if (errorMsg) btn.title = errorMsg;
                        setTimeout(() => { btn.textContent = oldTxt; btn.title = ""; }, 3000);
                    } else if (!active) {
                        // Just finished normally
                        init();
                    }
                }
            }
        });
    };
    window.aiHintsSetup = (card, hints) => { 
        let calcId = card ? card.id : 'temp';
        const ord = card ? card.ord : getCardOrd();
        if (calcId === 'temp') {
            const firstJson = document.querySelector('.ai-hints-json');
            if (firstJson) {
                calcId = 'h' + hashCode(firstJson.textContent);
            } else {
                const qa = document.getElementById('qa') || document.body;
                calcId = 'h' + hashCode(qa.innerText || qa.textContent || '');
            }
        }
        const setupKey = JSON.stringify({ card: { id: String(calcId), ord: ord }, hints: hints || null });
        const currentAnswerState = isAnswerSide();
        const existingContainer = document.querySelector('.ai-hints-container');
        const hasData = hints != null || document.querySelector('.ai-hints-json');
        const isEmptyContainer = existingContainer && !existingContainer.querySelector('.ai-hints-list') && !existingContainer.querySelector('.ai-hints-hint-list');
        const existingCardId = existingContainer && existingContainer.getAttribute ? existingContainer.getAttribute('data-ai-hints-card-id') : null;
        const existingCardOrd = existingContainer && existingContainer.getAttribute ? existingContainer.getAttribute('data-ai-hints-card-ord') : null;
        const sameRenderedCard = existingContainer && card &&
            String(existingCardId) === String(card.id) &&
            (existingCardOrd === null || existingCardOrd === undefined || existingCardOrd === '' || String(existingCardOrd) === String(card.ord));
        
        // If we have an existing container but we are doing a fresh setup (e.g. card changed),
        // we must ensure we don't bail out due to a stale setupKey.
        if (window.aiHintsLastSetupKey === setupKey && existingContainer && (!hasData || !isEmptyContainer) && window.aiHintsLastAnswerState === currentAnswerState) {
            return;
        }

        if (hints == null && sameRenderedCard && !isEmptyContainer && !hasData) {
            window.aiHintsLastSetupKey = setupKey;
            window.aiHintsLastAnswerState = currentAnswerState;
            window.aiHintsCurrentCard = card;
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
    
    if (window.aiHintsInterval) {
        clearInterval(window.aiHintsInterval);
        window.aiHintsInterval = null;
    }
    
    if (!isAddonActive) {
        window.aiHintsInterval = setInterval(() => {
            // Detect card change in standalone mode (no Python to trigger setup)
            const currentId = window.aiHintsCurrentCard ? window.aiHintsCurrentCard.id : 'temp';
            const currentOrd = getCardOrd();
            
            // Check for clues in the DOM that the card changed
            const cloze = document.querySelector('.cloze');
            const clozeClass = cloze ? cloze.className : '';
            
            const stateToken = currentId + '_' + currentOrd + '_' + clozeClass;
            if (window.aiHintsLastStateToken && window.aiHintsLastStateToken !== stateToken) {
                // Card or cloze changed! Reset state to force re-scan of JSON blocks
                window.aiHintsLastSetupKey = undefined;
                window.aiHintsCurrentCard = { id: currentId, ord: currentOrd };
                document.querySelectorAll('.ai-hints-container-rendered').forEach(e => e.remove());
                document.querySelectorAll('.ai-hints-json').forEach(e => delete e.dataset.aiHintsRendered);
            }
            window.aiHintsLastStateToken = stateToken;
            
            init();
        }, 500);
    }

    // Cross-Platform Keyboard Shortcuts handler
    if (!window.aiHintsKeyboardListenerAdded) {
        window.aiHintsKeyboardListenerAdded = true;
        document.addEventListener('keydown', (event) => {
            // Ignore if user is editing/typing in any input field
            if (document.activeElement && (
                document.activeElement.isContentEditable || 
                document.activeElement.tagName === 'INPUT' || 
                document.activeElement.tagName === 'TEXTAREA'
            )) {
                return;
            }

            const uiCfg = window.aiHintsUiConfig || {};
            const mobileCfg = window.aiHintsMobileConfig || {};
            const defaultShortcuts = {
                modifier: "alt",
                generate: "1",
                "toggle-options": "3",
                "toggle-hints": "2",
                clear: "4",
                refresh: "5",
                "show-json": "6"
            };
            const shortcuts = Object.assign({}, defaultShortcuts, uiCfg.shortcuts || mobileCfg.shortcuts || {});

            // Check modifier key
            const reqModifier = (shortcuts.modifier || 'alt').toLowerCase();
            let modifierMatch = false;
            if (reqModifier === 'none') {
                modifierMatch = !event.altKey && !event.ctrlKey && !event.shiftKey && !event.metaKey;
            } else if (reqModifier === 'alt') {
                modifierMatch = event.altKey && !event.ctrlKey && !event.shiftKey && !event.metaKey;
            } else if (reqModifier === 'ctrl') {
                modifierMatch = event.ctrlKey && !event.altKey && !event.shiftKey && !event.metaKey;
            } else if (reqModifier === 'shift') {
                modifierMatch = event.shiftKey && !event.altKey && !event.ctrlKey && !event.metaKey;
            } else if (reqModifier === 'meta') {
                modifierMatch = event.metaKey && !event.altKey && !event.ctrlKey && !event.shiftKey;
            }

            if (!modifierMatch) return;

            // Match keys
            const pressedKey = event.key.toLowerCase();
            
            // Helper to click button based on text/emoji
            const clickButton = (textPart, emoji) => {
                const btns = document.querySelectorAll('.ai-hints-btn');
                for (const btn of btns) {
                    const txt = btn.textContent || "";
                    if (txt.includes(textPart) || txt.includes(emoji)) {
                        btn.click();
                        return true;
                    }
                }
                return false;
            };

            // Check actions
            if (shortcuts.generate && pressedKey === shortcuts.generate.toLowerCase()) {
                event.preventDefault();
                clickButton("Generate", "✨") || clickButton("Regenerate", "✨");
            } else if (shortcuts["toggle-hints"] && pressedKey === shortcuts["toggle-hints"].toLowerCase()) {
                event.preventDefault();
                clickButton("Hints", "💡");
            } else if (shortcuts["toggle-options"] && pressedKey === shortcuts["toggle-options"].toLowerCase()) {
                event.preventDefault();
                clickButton("Options", "🎯");
            } else if (shortcuts.clear && pressedKey === shortcuts.clear.toLowerCase()) {
                event.preventDefault();
                clickButton("Clear", "🗑️");
            } else if (shortcuts.refresh && pressedKey === shortcuts.refresh.toLowerCase()) {
                event.preventDefault();
                clickButton("Refresh", "🔄");
            } else if (shortcuts["show-json"] && pressedKey === shortcuts["show-json"].toLowerCase()) {
                event.preventDefault();
                clickButton("JSON", "📝");
            }
        });
    }
})();
