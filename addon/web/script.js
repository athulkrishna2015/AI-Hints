(function() {
    function setupAIHints() {
        let container = document.querySelector('.ai-hints-container');
        const jsonBlock = document.querySelector('.ai-hints-json');
        const cardBody = document.body;

        if (jsonBlock && !container) {
            // Build container from JSON
            try {
                const options = JSON.parse(jsonBlock.innerText);
                container = document.createElement('div');
                container.className = 'ai-hints-container';
                container.innerHTML = `
                    <hr>
                    <b>AI Generated Options:</b>
                    <ul class="ai-hints-list">
                        ${options.map(opt => `<li>${opt}</li>`).join('')}
                    </ul>
                `;
                // Append near the JSON block or at the end
                jsonBlock.parentNode.insertBefore(container, jsonBlock.nextSibling);
            } catch (e) {
                console.error("AI-Hints: Failed to parse JSON options", e);
            }
        }

        if (container) {
            const list = container.querySelector('.ai-hints-list');
            if (list) {
                // Shuffle items
                const items = Array.from(list.children);
                for (let i = items.length - 1; i > 0; i--) {
                    const j = Math.floor(Math.random() * (i + 1));
                    [items[i], items[j]] = [items[j], items[i]];
                }
                items.forEach(item => list.appendChild(item));
                
                // Hide list initially
                list.classList.add('ai-hints-hidden');
            }

            // Create buttons
            const btnContainer = document.createElement('div');
            btnContainer.style.marginTop = '10px';

            const showBtn = document.createElement('button');
            showBtn.innerText = 'Show Options';
            showBtn.className = 'ai-hints-btn';
            showBtn.onclick = function() {
                list.classList.toggle('ai-hints-hidden');
                showBtn.innerText = list.classList.contains('ai-hints-hidden') ? 'Show Options' : 'Hide Options';
            };

            const regenBtn = document.createElement('button');
            regenBtn.innerText = 'Regenerate';
            regenBtn.className = 'ai-hints-btn ai-hints-btn-secondary';
            regenBtn.onclick = function() {
                regenBtn.disabled = true;
                regenBtn.innerText = 'Regenerating...';
                pycmd('ai_hints_generate');
            };

            btnContainer.appendChild(showBtn);
            btnContainer.appendChild(regenBtn);
            container.insertBefore(btnContainer, list);
        } else {
            // No hints yet, add generate button at the bottom of the card
            const genBtn = document.createElement('button');
            genBtn.innerText = 'Generate AI Hints';
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

    // Run setup
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', setupAIHints);
    } else {
        setupAIHints();
    }
})();
