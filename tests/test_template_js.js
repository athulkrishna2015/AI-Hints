
const fs = require('fs');
const path = require('path');

// Mock browser environment
global.document = {
    head: { appendChild: () => {} },
    body: { classList: { contains: () => false } },
    getElementById: (id) => null,
    querySelectorAll: (selector) => {
        if (selector === '.ai-hints-json') {
            return [{
                textContent: JSON.stringify({
                    "hints": ["Hint 1"],
                    "options": ["Option 1", "Option 2"],
                    "correct_answer": "Option 1"
                }),
                dataset: {},
                nextSibling: null,
                parentNode: {
                    insertBefore: (newNode, referenceNode) => {
                        console.log("SUCCESS: Button container inserted into DOM");
                        // Basic verification of created elements
                        const btnBox = newNode.querySelector('.ai-hints-btn-box');
                        if (btnBox) {
                            const btns = btnBox.querySelectorAll('button');
                            console.log(`Found ${btns.length} buttons: ${Array.from(btns).map(b => b.textContent).join(', ')}`);
                        }
                    }
                }
            }];
        }
        return [];
    },
    querySelector: (selector) => null,
    createElement: (tag) => {
        const el = {
            tagName: tag.toUpperCase(),
            className: '',
            textContent: '',
            style: {},
            dataset: {},
            appendChild: (child) => {
                if (!el.children) el.children = [];
                el.children.push(child);
            },
            querySelector: (sel) => {
                if (!el.children) return null;
                return el.children.find(c => c.className === sel.replace('.', ''));
            },
            querySelectorAll: (sel) => {
                if (!el.children) return [];
                return el.children.filter(c => c.tagName.toLowerCase() === sel);
            },
            onclick: null
        };
        return el;
    },
    readyState: 'complete',
    addEventListener: () => {}
};

global.window = {
    aiHintsUiConfig: null,
    focus: () => {}
};

global.setInterval = () => {};

// Load the template script
const scriptPath = path.join(__dirname, '..', 'addon', 'web', 'template.js');
const scriptContent = fs.readFileSync(scriptPath, 'utf8');

console.log("Running template.js logic test...");
eval(scriptContent);
console.log("Test finished.");
