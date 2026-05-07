(function() {
    function setupAIHints() {
        let container = document.querySelector('.ai-hints-container');
        const jsonBlock = document.querySelector('.ai-hints-json');
        const cardBody = document.body;

        if (jsonBlock && !container) {
            try {
                const data = JSON.parse(jsonBlock.innerText);
                container = document.createElement('div');
                container.className = 'ai-hints-container';
                
                let hintsHtml = "";
                if (data.hints && data.hints.length > 0) {
                    hintsHtml = `<b>AI Hints:</b><ul class="ai-hints-hint-list">${data.hints.map(h => `<li>${h}</li>`).join('')}</ul>`;
                }
                
                let optionsHtml = "";
                if (data.options && data.options.length > 0) {
                    optionsHtml = `<b>AI Options:</b><ul class="ai-hints-list">${data.options.map(o => `<li>${o}</li>`).join('')}</ul>`;
                }

                container.innerHTML = `
                    <hr>
                    ${hintsHtml}
                    ${optionsHtml}
                `;
                jsonBlock.parentNode.insertBefore(container, jsonBlock.nextSibling);
                // Inherit data attributes
                container.setAttribute('data-show-hints', jsonBlock.getAttribute('data-show-hints'));
                container.setAttribute('data-show-options', jsonBlock.getAttribute('data-show-options'));
            } catch (e) {
                console.error("AI-Hints: Failed to parse JSON options", e);
            }
        }

        if (container) {
            const optionsList = container.querySelector('.ai-hints-list');
            const hintsList = container.querySelector('.ai-hints-hint-list');
            
            const showHintsCfg = container.getAttribute('data-show-hints') !== 'false';
            const showOptionsCfg = container.getAttribute('data-show-options') !== 'false';
            
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
            btnContainer.style.marginTop = '10px';

            if (hintsList && showHintsCfg) {
                const hintBtn = document.createElement('button');
                hintBtn.innerText = 'Show Hints';
                hintBtn.className = 'ai-hints-btn';
                hintBtn.onclick = function() {
                    hintsList.classList.toggle('ai-hints-hidden');
                    hintBtn.innerText = hintsList.classList.contains('ai-hints-hidden') ? 'Show Hints' : 'Hide Hints';
                };
                btnContainer.appendChild(hintBtn);
            }

            if (optionsList && showOptionsCfg) {
                const showBtn = document.createElement('button');
                showBtn.innerText = 'Show Options';
                showBtn.className = 'ai-hints-btn';
                showBtn.onclick = function() {
                    optionsList.classList.toggle('ai-hints-hidden');
                    showBtn.innerText = optionsList.classList.contains('ai-hints-hidden') ? 'Show Options' : 'Hide Options';
                };
                btnContainer.appendChild(showBtn);
            }

            const regenBtn = document.createElement('button');
            regenBtn.innerText = 'Regenerate';
            regenBtn.className = 'ai-hints-btn ai-hints-btn-secondary';
            regenBtn.onclick = function() {
                regenBtn.disabled = true;
                regenBtn.innerText = 'Regenerating...';
                pycmd('ai_hints_generate');
            };
            btnContainer.appendChild(regenBtn);

            // Insert buttons at the top of the container
            container.insertBefore(btnContainer, container.firstChild.nextSibling);
        } else {
            const genBtn = document.createElement('button');
            genBtn.innerText = 'Generate AI Hints/Options';
            genBtn.className = 'ai-hints-btn';
            genBtn.style.display = 'block';
            genBtn.style.margin = '20px auto';
            genBtn.onclick = function() {
                genBtn.disabled = true;
                genBtn.innerText = 'Generating...';
                pycmd('ai_hints_generate');
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
