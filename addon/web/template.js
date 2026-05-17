/**
 * AI-Hints Standalone Template Script
 * This script allows AI Hints and Options to be displayed on any device (AnkiDroid, AnkiMobile, Web)
 * even without the Python addon installed.
 * 
 * Instructions: Add <script src="_ai_hints_template.js"></script> to your card template,
 * or paste this code inside a <script> tag.
 */
(function() {
    console.log("AI-Hints: Template script initializing...");

    // 1. Configuration & Styling
    const STYLES = `
        .ai-hints-container { margin-top: 15px; padding: 12px; border: 1px dashed #aaa; border-radius: 10px; background-color: rgba(128,128,128,0.08); text-align: left; font-family: sans-serif; clear: both; }
        .ai-hints-btn-box { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 10px; }
        .ai-hints-btn { padding: 6px 12px; cursor: pointer; border-radius: 6px; border: 1px solid #999; background-color: #f0f0f0; color: #222; font-size: 13px; font-weight: 500; transition: background 0.2s; -webkit-tap-highlight-color: transparent; }
        .ai-hints-btn:hover { background-color: #e0e0e0; }
        .ai-hints-btn:active { background-color: #d0d0d0; transform: translateY(1px); }
        .ai-hints-list, .ai-hints-hint-list { margin-top: 10px; padding-left: 20px; display: none; }
        .ai-hints-list li, .ai-hints-hint-list li { margin-bottom: 6px; line-height: 1.4; }
        .ai-hints-correct { border-left: 4px solid #2ecc71; background-color: rgba(46, 204, 113, 0.15); padding-left: 8px; font-weight: 600; border-radius: 0 4px 4px 0; }
        .nightMode .ai-hints-container { background-color: rgba(255,255,255,0.05); border-color: #555; }
        .nightMode .ai-hints-btn { background-color: #333; color: #eee; border-color: #666; }
        .nightMode .ai-hints-btn:hover { background-color: #444; }
        .ai-hints-title { font-weight: bold; margin-bottom: 4px; display: block; font-size: 0.9em; opacity: 0.8; }
        .ai-hints-json-view { margin-top: 10px; padding: 8px; background: rgba(0,0,0,0.05); border-radius: 5px; font-family: monospace; font-size: 11px; white-space: pre-wrap; overflow-x: auto; }
        .nightMode .ai-hints-json-view { background: rgba(255,255,255,0.05); }
    `;

    function isAnswerSide() {
        return !!document.getElementById('answer') || !!document.querySelector('.answer') || document.body.classList.contains('answer');
    }

    function getCardOrd() {
        const cloze = document.querySelector('.cloze');
        if (cloze) {
            const match = cloze.className.match(/\bc(\d+)\b/);
            if (match) return parseInt(match[1]) - 1;
        }
        return 0;
    }

    function shuffle(array) {
        let m = array.length, t, i;
        while (m) {
            i = Math.floor(Math.random() * m--);
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

    function renderSection(parent, title, items, isCorrectFn) {
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

        if (title.toLowerCase().includes('option')) shuffle(listItems);
        listItems.forEach(li => list.appendChild(li));
        parent.appendChild(list);
        return list;
    }

    function init() {
        // Prevent running if addon is active
        if (window.aiHintsUiConfig || document.querySelector('.ai-hints-actions')) return;

        const jsonBlocks = document.querySelectorAll('.ai-hints-json');
        if (jsonBlocks.length === 0) return;

        console.log("AI-Hints: Found " + jsonBlocks.length + " JSON data blocks.");

        // Config from window
        const cfg = window.aiHintsMobileConfig || {};
        const useEmojis = cfg.useEmojis === true;
        const showExtra = cfg.showExtraButtons === true;

        const labels = {
            hints: useEmojis ? "💡 Hints" : "Show Hints",
            options: useEmojis ? "🎯 Options" : "Show Options",
            refresh: useEmojis ? "🔄" : "Refresh",
            json: useEmojis ? "📝" : "JSON",
            hideHints: useEmojis ? "💡" : "Hide Hints",
            hideOptions: useEmojis ? "🎯" : "Hide Options"
        };

        if (!document.getElementById('ai-hints-template-styles')) {
            const s = document.createElement('style');
            s.id = 'ai-hints-template-styles';
            s.textContent = STYLES;
            document.head.appendChild(s);
        }

        const ord = getCardOrd();
        const cardKey = 'c' + (ord + 1);
        const onAnswer = isAnswerSide();

        jsonBlocks.forEach(block => {
            if (block.dataset.aiHintsRendered) return;
            try {
                let data = JSON.parse(block.textContent);
                if (data[cardKey]) data = data[cardKey];
                if (!data || (!data.hints && !data.options)) return;

                console.log("AI-Hints: Rendering buttons for key " + cardKey);

                const container = document.createElement('div');
                container.className = 'ai-hints-container';
                
                const btnBox = document.createElement('div');
                btnBox.className = 'ai-hints-btn-box';
                container.appendChild(btnBox);

                const hList = renderSection(container, "AI Hints:", data.hints);
                const oList = renderSection(container, "AI Options:", data.options, (txt) => 
                    onAnswer && data.correct_answer && txt.trim().toLowerCase() === data.correct_answer.trim().toLowerCase()
                );

                if (hList) {
                    const btn = document.createElement('button');
                    btn.className = 'ai-hints-btn';
                    btn.textContent = labels.hints;
                    btn.onclick = () => {
                        const show = hList.style.display !== 'block';
                        hList.style.display = show ? 'block' : 'none';
                        btn.textContent = show ? labels.hideHints : labels.hints;
                        if (show) renderMath(hList);
                    };
                    btnBox.appendChild(btn);
                }

                if (oList) {
                    const btn = document.createElement('button');
                    btn.className = 'ai-hints-btn';
                    btn.textContent = labels.options;
                    btn.onclick = () => {
                        const show = oList.style.display !== 'block';
                        oList.style.display = show ? 'block' : 'none';
                        btn.textContent = show ? labels.hideOptions : labels.options;
                        if (show) renderMath(oList);
                    };
                    btnBox.appendChild(btn);
                }

                if (showExtra) {
                    const refBtn = document.createElement('button');
                    refBtn.className = 'ai-hints-btn';
                    refBtn.textContent = labels.refresh;
                    refBtn.title = "Refresh UI";
                    refBtn.onclick = () => {
                        delete block.dataset.aiHintsRendered;
                        container.remove();
                        init();
                    };
                    btnBox.appendChild(refBtn);

                    const jsonBtn = document.createElement('button');
                    jsonBtn.className = 'ai-hints-btn';
                    jsonBtn.textContent = labels.json;
                    jsonBtn.title = "View JSON";
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

                const target = document.querySelector('ai-hints') || block.nextSibling;
                if (target === block.nextSibling) {
                    block.parentNode.insertBefore(container, target);
                } else {
                    target.innerHTML = '';
                    target.appendChild(container);
                }
                block.dataset.aiHintsRendered = "true";

            } catch (e) {
                console.error("AI-Hints Error: ", e);
            }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
    // Periodic check for dynamic rendering
    setInterval(init, 1000);
})();
