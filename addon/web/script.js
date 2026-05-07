(function() {
    function sendCommand(command) {
        if (typeof pycmd === 'function') {
            pycmd(command);
        }
    }

    function restartSpeedFocusTimer() {
        sendCommand('ai_hints_restart_speed_focus');
    }

    function currentCard() {
        return window.aiHintsCurrentCard || { id: '', ord: null };
    }

    function showGenerateOnCard() {
        const cfg = window.aiHintsUiConfig || {};
        return cfg.show_on_card !== false;
    }

    function hasCardScope(element) {
        return Boolean(element.dataset.aiHintsCardId || element.dataset.aiHintsCardOrd);
    }

    function matchesCurrentCard(element) {
        const current = currentCard();
        const currentId = current.id == null ? '' : String(current.id);
        const currentOrd = current.ord == null ? '' : String(current.ord);

        if (element.dataset.aiHintsCardId && currentId) {
            return element.dataset.aiHintsCardId === currentId;
        }
        if (element.dataset.aiHintsCardOrd && currentOrd) {
            return element.dataset.aiHintsCardOrd === currentOrd;
        }
        return !hasCardScope(element);
    }

    function selectCurrentBlock(selector) {
        const blocks = Array.from(document.querySelectorAll(selector));
        if (blocks.length === 0) {
            return null;
        }

        const scopedMatch = blocks.find(function(block) {
            return hasCardScope(block) && matchesCurrentCard(block);
        });
        if (scopedMatch) {
            return scopedMatch;
        }

        const legacyMatch = blocks.find(function(block) {
            return !hasCardScope(block);
        });
        return legacyMatch || null;
    }

    function hideOtherContainers(activeContainer) {
        document.querySelectorAll('.ai-hints-container').forEach(function(container) {
            if (container !== activeContainer) {
                container.style.display = 'none';
            }
        });
    }

    function copyCardAttrs(source, target) {
        ['showHints', 'showOptions', 'aiHintsCardId', 'aiHintsCardOrd'].forEach(function(key) {
            if (source.dataset[key] != null) {
                target.dataset[key] = source.dataset[key];
            }
        });
    }

    function isEditableTarget(target) {
        if (!(target instanceof Element)) {
            return false;
        }
        return Boolean(target.closest('input, textarea, select, [contenteditable="true"], [contenteditable=""]'));
    }

    function createListSection(title, className, items) {
        if (!Array.isArray(items) || items.length === 0) {
            return null;
        }

        const fragment = document.createDocumentFragment();
        const heading = document.createElement('b');
        heading.textContent = title;
        fragment.appendChild(heading);
        fragment.appendChild(document.createElement('br'));

        const list = document.createElement('ul');
        list.className = className;
        items.forEach(function(item) {
            const li = document.createElement('li');
            li.textContent = String(item);
            list.appendChild(li);
        });
        fragment.appendChild(list);
        return fragment;
    }

    function isImageOcclusionClick(target) {
        if (!(target instanceof Element)) {
            return false;
        }

        const explicitTarget = target.closest([
            '.image-occlusion',
            '.image-occlusion-container',
            '.image-occlusion-wrapper',
            '.anki-image-occlusion',
            '.io-container',
            '.io-overlay',
            '.io-question-mask',
            '.io-answer-mask',
            '.io-mask',
            '.qshape',
            '.ashape',
            '[class*="image-occlusion"]',
            '[id*="image-occlusion"]',
            '[class^="io-"]',
            '[class*=" io-"]',
            '[id^="io-"]'
        ].join(','));
        if (explicitTarget) {
            return true;
        }

        const svgTarget = target.closest('svg');
        if (!svgTarget) {
            return false;
        }

        const tagName = target.tagName.toLowerCase();
        const isMaskShape = ['rect', 'path', 'polygon', 'circle', 'ellipse', 'image'].includes(tagName);
        const cardHasImageOcclusion = Boolean(document.querySelector(
            '.image-occlusion, .image-occlusion-container, .anki-image-occlusion, .io-overlay, .qshape, .ashape'
        ));
        return isMaskShape && cardHasImageOcclusion;
    }

    function revealAIHints() {
        const container = selectCurrentBlock('.ai-hints-container');
        if (!container) return false;

        const hintsList = container.querySelector('.ai-hints-hint-list');
        const optionsList = container.querySelector('.ai-hints-list');
        const hintBtn = document.querySelector('[data-ai-hints-action="toggle-hints"]');
        const showBtn = document.querySelector('[data-ai-hints-action="toggle-options"]');
        
        const showHintsCfg = container.getAttribute('data-show-hints') !== 'false';
        const showOptionsCfg = container.getAttribute('data-show-options') !== 'false';

        let revealed = false;
        if (hintsList && showHintsCfg && hintsList.classList.contains('ai-hints-hidden')) {
            hintsList.classList.remove('ai-hints-hidden');
            if (hintBtn) {
                hintBtn.innerText = 'Hide Hints';
            }
            if (showBtn) {
                showBtn.style.display = 'inline-block';
            }
            revealed = true;
        }
        if (optionsList && showOptionsCfg && optionsList.classList.contains('ai-hints-hidden')) {
            optionsList.classList.remove('ai-hints-hidden');
            if (showBtn) {
                showBtn.style.display = 'inline-block';
                showBtn.innerText = 'Hide Options';
            }
            revealed = true;
        }
        if (revealed) {
            restartSpeedFocusTimer();
        }
        return revealed;
    }

    function setupAIHints() {
        const current = currentCard();
        if (!current.id && current.ord == null) {
            return;
        }

        const cardKey = (current.id || '') + '_' + (current.ord || '0');
        const cardBody = document.getElementById('qa') || document.body;
        
        // Hide all containers initially, then show the matched one
        document.querySelectorAll('.ai-hints-container').forEach(function(el) {
            el.style.display = 'none';
        });

        // Cleanup: Remove any dynamic buttons/actions from previous cards
        document.querySelectorAll('.ai-hints-actions').forEach(function(el) {
            el.remove();
        });

        let container = selectCurrentBlock('.ai-hints-container');
        const jsonBlock = selectCurrentBlock('.ai-hints-json');

        if (jsonBlock && !container) {
            try {
                const rawData = (jsonBlock.textContent || jsonBlock.innerText || '').trim();
                const data = JSON.parse(rawData);
                container = document.createElement('div');
                container.className = 'ai-hints-container';

                container.appendChild(document.createElement('hr'));
                const hintsSection = createListSection('AI Hints:', 'ai-hints-hint-list', data.hints);
                const optionsSection = createListSection('AI Options:', 'ai-hints-list', data.options);
                if (hintsSection) {
                    container.appendChild(hintsSection);
                }
                if (optionsSection) {
                    container.appendChild(optionsSection);
                }
                jsonBlock.parentNode.insertBefore(container, jsonBlock.nextSibling);
                copyCardAttrs(jsonBlock, container);
            } catch (e) {
                console.error("AI-Hints: Failed to parse JSON options", e);
            }
        }

        const uiCfg = window.aiHintsUiConfig || {};
        const showOnCard = uiCfg.show_on_card !== false;
        
        if (!showOnCard && !container) {
            return;
        }

        const btnContainer = document.createElement('div');
        btnContainer.className = 'ai-hints-actions';
        btnContainer.style.marginTop = '10px';
        btnContainer.style.textAlign = 'center';

        let hintsList = null;
        let optionsList = null;
        let showHintsCfg = true;
        let showOptionsCfg = true;

        if (container) {
            // Only show if it matches the current card
            if (matchesCurrentCard(container)) {
                container.style.display = 'block';
                hideOtherContainers(container);
                optionsList = container.querySelector('.ai-hints-list');
                hintsList = container.querySelector('.ai-hints-hint-list');
                
                showHintsCfg = container.getAttribute('data-show-hints') !== 'false';
                showOptionsCfg = container.getAttribute('data-show-options') !== 'false';
                
                // Reset and shuffle options
                if (optionsList) {
                    const items = Array.from(optionsList.children);
                    for (let i = items.length - 1; i > 0; i--) {
                        const j = Math.floor(Math.random() * (i + 1));
                        [items[i], items[j]] = [items[j], items[i]];
                    }
                    items.forEach(item => optionsList.appendChild(item));
                    optionsList.classList.add('ai-hints-hidden');
                }

                if (hintsList) {
                    hintsList.classList.add('ai-hints-hidden');
                }
            } else {
                container.style.display = 'none';
            }
        }

        const triggerGenerate = function(btn) {
            restartSpeedFocusTimer();
            btn.disabled = true;
            btn.innerText = 'Generating...';
            sendCommand('ai_hints_generate');
        };

        // Show Options Button
        if (showOptionsCfg) {
            const optBtn = document.createElement('button');
            optBtn.innerText = 'Show Options';
            optBtn.className = 'ai-hints-btn';
            optBtn.dataset.aiHintsAction = 'toggle-options';
            optBtn.onclick = function() {
                if (optionsList) {
                    restartSpeedFocusTimer();
                    const isHidden = optionsList.classList.contains('ai-hints-hidden');
                    optionsList.classList.toggle('ai-hints-hidden');
                    optBtn.innerText = isHidden ? 'Hide Options' : 'Show Options';
                } else {
                    triggerGenerate(optBtn);
                }
            };
            btnContainer.appendChild(optBtn);
        }

        // Show Hints Button
        if (showHintsCfg) {
            const hintBtn = document.createElement('button');
            hintBtn.innerText = 'Show Hints';
            hintBtn.className = 'ai-hints-btn';
            hintBtn.dataset.aiHintsAction = 'toggle-hints';
            hintBtn.onclick = function() {
                if (hintsList) {
                    restartSpeedFocusTimer();
                    const isHidden = hintsList.classList.contains('ai-hints-hidden');
                    hintsList.classList.toggle('ai-hints-hidden');
                    hintBtn.innerText = isHidden ? 'Hide Hints' : 'Show Hints';
                } else {
                    triggerGenerate(hintBtn);
                }
            };
            btnContainer.appendChild(hintBtn);
        }

        // Refresh Button
        const refreshBtn = document.createElement('button');
        refreshBtn.innerText = 'Refresh';
        refreshBtn.className = 'ai-hints-btn ai-hints-btn-secondary';
        refreshBtn.title = 'Refresh hints from card cache';
        refreshBtn.onclick = function() {
            restartSpeedFocusTimer();
            refreshBtn.disabled = true;
            refreshBtn.innerText = 'Refreshing...';
            sendCommand('ai_hints_refresh');
            // Auto-reset if refresh takes too long or fails to reload page
            setTimeout(function() {
                if (refreshBtn) {
                    refreshBtn.disabled = false;
                    refreshBtn.innerText = 'Refresh';
                }
            }, 2000);
        };
        btnContainer.appendChild(refreshBtn);

        // Regenerate Button
        const regenBtn = document.createElement('button');
        regenBtn.innerText = container ? 'Regenerate' : 'Generate';
        regenBtn.className = 'ai-hints-btn ai-hints-btn-secondary';
        regenBtn.onclick = function() {
            triggerGenerate(regenBtn);
        };
        btnContainer.appendChild(regenBtn);

        if (container && container.style.display !== 'none') {
            const separator = container.querySelector('hr');
            container.insertBefore(btnContainer, separator ? separator.nextSibling : container.firstChild);
        } else {
            btnContainer.style.margin = '20px auto';
            cardBody.appendChild(btnContainer);
        }
    }

    window.aiHintsSetup = function(cardData) {
        window.aiHintsCurrentCard = cardData;
        setupAIHints();
    };

    // Single global listener
    if (!window.aiHintsClickBound) {
        window.aiHintsClickBound = true;
        document.addEventListener('click', function(event) {
            if (!event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) {
                return;
            }

            const target = event.target;
            if (isEditableTarget(target)) {
                return;
            }

            const isClozeClick = target instanceof Element && target.closest('.cloze');
            if (!isClozeClick && !isImageOcclusionClick(target)) {
                return;
            }

            if (revealAIHints()) {
                event.preventDefault();
                event.stopPropagation();
            }
        }, true);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', setupAIHints);
    } else {
        setupAIHints();
    }
})();
