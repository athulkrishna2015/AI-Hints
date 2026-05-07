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

    function setupAIHints() {
        const current = currentCard();
        const cardKey = (current.id || '') + '_' + (current.ord || '0');
        const cardBody = document.getElementById('qa') || document.body;

        if (cardBody && cardBody.dataset.aiHintsLastCardKey === cardKey) {
            // If we think we've already processed this card, verify buttons exist
            if (document.querySelector('.ai-hints-btn, .ai-hints-actions')) {
                return;
            }
        }
        if (cardBody) {
            cardBody.dataset.aiHintsLastCardKey = cardKey;
        }

        // Cleanup: Remove any dynamic buttons or containers from previous cards
        // that might have been appended to document.body or are no longer valid.
        document.querySelectorAll('.ai-hints-actions, .ai-hints-btn, .ai-hints-btn-secondary').forEach(function(el) {
            el.remove();
        });
        
        // Hide containers that don't match the current card
        document.querySelectorAll('.ai-hints-container').forEach(function(container) {
            if (!matchesCurrentCard(container)) {
                container.style.display = 'none';
            }
        });

        let container = selectCurrentBlock('.ai-hints-container');
        const jsonBlock = selectCurrentBlock('.ai-hints-json');

        if (jsonBlock && !container) {
            try {
                const data = JSON.parse(jsonBlock.innerText);
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

        if (container) {
            container.style.display = 'block'; // Ensure matched container is visible
            hideOtherContainers(container);
            const optionsList = container.querySelector('.ai-hints-list');
            const hintsList = container.querySelector('.ai-hints-hint-list');
            
            const showHintsCfg = container.getAttribute('data-show-hints') !== 'false';
            const showOptionsCfg = container.getAttribute('data-show-options') !== 'false';
            let showBtn = null;
            let hintBtn = null;
            
            // Shuffle options
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

            // Create buttons
            const btnContainer = document.createElement('div');
            btnContainer.className = 'ai-hints-actions';
            btnContainer.style.marginTop = '10px';

            if (optionsList && showOptionsCfg) {
                showBtn = document.createElement('button');
                showBtn.innerText = 'Show Options';
                showBtn.className = 'ai-hints-btn';
                showBtn.onclick = function() {
                    restartSpeedFocusTimer();
                    optionsList.classList.toggle('ai-hints-hidden');
                    showBtn.innerText = optionsList.classList.contains('ai-hints-hidden') ? 'Show Options' : 'Hide Options';
                };
                
                // Initially hide if hints button exists
                if (hintsList && showHintsCfg) {
                    showBtn.style.display = 'none';
                }
                btnContainer.appendChild(showBtn);
            }

            if (hintsList && showHintsCfg) {
                hintBtn = document.createElement('button');
                hintBtn.innerText = 'Show Hints';
                hintBtn.className = 'ai-hints-btn';
                hintBtn.onclick = function() {
                    restartSpeedFocusTimer();
                    const isHidden = hintsList.classList.contains('ai-hints-hidden');
                    hintsList.classList.toggle('ai-hints-hidden');
                    hintBtn.innerText = isHidden ? 'Hide Hints' : 'Show Hints';
                    
                    // Show options button when hints are shown
                    if (isHidden && showBtn) {
                        showBtn.style.display = 'inline-block';
                    }
                };
                btnContainer.appendChild(hintBtn);
            }

            const regenBtn = document.createElement('button');
            regenBtn.innerText = 'Regenerate';
            regenBtn.className = 'ai-hints-btn ai-hints-btn-secondary';
            regenBtn.onclick = function() {
                restartSpeedFocusTimer();
                regenBtn.disabled = true;
                regenBtn.innerText = 'Regenerating...';
                sendCommand('ai_hints_generate');
            };
            btnContainer.appendChild(regenBtn);

            // Insert buttons at the top of the container
            container.insertBefore(btnContainer, container.firstChild.nextSibling);

            function revealAIHints() {
                let revealed = false;
                if (hintsList && showHintsCfg) {
                    hintsList.classList.remove('ai-hints-hidden');
                    if (hintBtn) {
                        hintBtn.innerText = 'Hide Hints';
                    }
                    if (showBtn) {
                        showBtn.style.display = 'inline-block';
                    }
                    revealed = true;
                }
                if (optionsList && showOptionsCfg) {
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
        } else {
            const genBtn = document.createElement('button');
            genBtn.innerText = 'Generate AI Hints/Options';
            genBtn.className = 'ai-hints-btn';
            genBtn.style.display = 'block';
            genBtn.style.margin = '20px auto';
            genBtn.onclick = function() {
                restartSpeedFocusTimer();
                genBtn.disabled = true;
                genBtn.innerText = 'Generating...';
                sendCommand('ai_hints_generate');
            };
            cardBody.appendChild(genBtn);
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', setupAIHints);
    } else {
        setupAIHints();
    }
})();
