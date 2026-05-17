
const fs = require('fs');
const path = require('path');

/**
 * Mock DOM Environment Factory
 */
function createMockDOM(env) {
    const { isAddonActive, hasData } = env;
    
    let renderedBlocks = [];
    const persistence = {};

    global.sessionStorage = {
        setItem: (key, val) => { persistence[key] = val; },
        getItem: (key) => persistence[key] || null
    };

    global.document = {
        head: { appendChild: () => {} },
        body: { 
            classList: { contains: () => false },
            appendChild: (el) => { renderedBlocks.push(el); }
        },
        getElementById: (id) => (id === 'qa') ? global.document.body : null,
        querySelectorAll: (selector) => {
            if (selector === '.ai-hints-json' && hasData) {
                return [{
                    textContent: JSON.stringify({ hints: ["H1"], options: ["O1"] }),
                    dataset: {},
                    parentNode: { insertBefore: (n, r) => renderedBlocks.push(n) }
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
                children: [],
                appendChild: (child) => el.children.push(child),
                querySelector: (sel) => el.children.find(c => c.className === sel.replace('.', '')),
                querySelectorAll: (sel) => {
                   if (sel === 'button') return el.children.filter(c => c.tagName === 'BUTTON');
                   return [];
                },
                remove: () => {}
            };
            return el;
        },
        readyState: 'complete',
        addEventListener: () => {}
    };

    global.window = {
        aiHintsUiConfig: isAddonActive ? { is_generating: false } : null,
        aiHintsMobileConfig: !isAddonActive ? { useEmojis: true, showExtraButtons: true } : null,
        focus: () => {}
    };

    if (isAddonActive) {
        global.pycmd = (cmd) => console.log(`[MOCK PYCMD] Executing: ${cmd}`);
    } else {
        delete global.pycmd;
    }

    return {
        getRendered: () => renderedBlocks
    };
}

const scriptPath = path.join(__dirname, '..', 'addon', 'web', 'template.js');
const scriptContent = fs.readFileSync(scriptPath, 'utf8');

console.log("--- TEST 1: DESKTOP MODE (Addon Active) ---");
const desktop = createMockDOM({ isAddonActive: true, hasData: true });
eval(scriptContent);
const desktopContainer = desktop.getRendered().find(el => el.className === 'ai-hints-container');
const desktopBtns = desktopContainer.querySelector('.ai-hints-btn-box').querySelectorAll('button');
const desktopLabels = desktopBtns.map(b => b.textContent);
console.log("Buttons found:", desktopLabels.join(', '));
if (!desktopLabels.includes("Regenerate")) throw new Error("Missing Regenerate button on Desktop");
if (!desktopLabels.includes("Clear")) throw new Error("Missing Clear button on Desktop");

console.log("\n--- TEST 2: MOBILE MODE (Standalone) ---");
const mobile = createMockDOM({ isAddonActive: false, hasData: true });
eval(scriptContent);
const mobileContainer = mobile.getRendered().find(el => el.className === 'ai-hints-container');
const mobileBtns = mobileContainer.querySelector('.ai-hints-btn-box').querySelectorAll('button');
const mobileLabels = mobileBtns.map(b => b.textContent);
console.log("Buttons found:", mobileLabels.join(', '));
if (mobileLabels.includes("Regenerate") || mobileLabels.includes("Generate AI Hints")) 
    throw new Error("Generate button should NOT appear on Mobile");
if (mobileLabels.includes("💡 Hints")) console.log("Emoji support verified");

console.log("\n--- TEST 3: NO DATA (Desktop) ---");
const noData = createMockDOM({ isAddonActive: true, hasData: false });
eval(scriptContent);
const allRendered = noData.getRendered();
const noDataContainer = allRendered.find(el => el.className === 'ai-hints-container');
if (!noDataContainer) throw new Error("Container not found in Desktop mode with no data");
const noDataBtns = noDataContainer.querySelector('.ai-hints-btn-box').querySelectorAll('button');
console.log("Buttons found:", noDataBtns.map(b => b.textContent).join(', '));
if (noDataBtns[0].textContent !== "Generate AI Hints") throw new Error("Should show 'Generate' when no data");

console.log("\nALL JS TESTS PASSED.");
