
const fs = require('fs');
const path = require('path');

/**
 * Mock DOM Environment Factory
 */
function createMockDOM(env) {
    const { isAddonActive, hasData } = env;
    
    let renderedBlocks = [];
    let jsonBlocks = [];
    if (hasData) {
        const jsonBlock = {
            textContent: JSON.stringify({ hints: ["H1"], options: ["O1"] }),
            dataset: {},
            parentNode: { insertBefore: (n, r) => renderedBlocks.push(n) },
            remove: () => { jsonBlocks = jsonBlocks.filter(item => item !== jsonBlock); }
        };
        jsonBlocks = [jsonBlock];
    }
    const persistence = {};

    global.sessionStorage = {
        setItem: (key, val) => { persistence[key] = val; },
        getItem: (key) => persistence[key] || null,
        removeItem: (key) => { delete persistence[key]; }
    };

    global.document = {
        head: { appendChild: () => {} },
        body: { 
            classList: { contains: () => false },
            appendChild: (el) => { renderedBlocks.push(el); }
        },
        getElementById: (id) => (id === 'qa') ? global.document.body : null,
        querySelectorAll: (selector) => {
            if (selector === '.ai-hints-container') return renderedBlocks.filter(el => el.className === 'ai-hints-container');
            if (selector === '.ai-hints-json') return jsonBlocks;
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
                remove: () => {
                    renderedBlocks = renderedBlocks.filter(item => item !== el);
                    jsonBlocks = jsonBlocks.filter(item => item !== el);
                }
            };
            return el;
        },
        readyState: 'complete',
        addEventListener: () => {}
    };

    if (!global.window) global.window = {};
    global.window = {
        ...global.window,
        aiHintsUiConfig: isAddonActive ? (global.window.aiHintsUiConfig || { is_generating: false }) : null,
        aiHintsMobileConfig: !isAddonActive ? { useEmojis: true, showExtraButtons: true } : null,
        focus: () => {}
    };

    if (isAddonActive) {
        global.pycmd = (cmd) => console.log(`[MOCK PYCMD] Executing: ${cmd}`);
    } else {
        delete global.pycmd;
    }

    return {
        getRendered: () => renderedBlocks,
        getJsonBlocks: () => jsonBlocks
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

console.log("\n--- TEST 4: AUTO-REVEAL CONFIG (Desktop) ---");
global.window.aiHintsCurrentCard = { id: 'card_reveal_test', ord: 0 };
// This is the global uiCfg that the eval'd script will use
global.window.aiHintsUiConfig = {
    manual_show_hints: true,
    manual_show_options: false,
    auto_reveal: false,
    is_generating: false
};
const revealTest = createMockDOM({ isAddonActive: true, hasData: true });
// Re-eval to ensure init() is defined with the new global window state
eval(scriptContent);

// Simulate receiving new data after manual generation
window.aiHintsUpdateData({ hints: ["Hint revealed!"], options: ["Option hidden"] });

// Find the last container (the one created by aiHintsUpdateData)
const allRenders = revealTest.getRendered();
const revealedContainer = allRenders[allRenders.length - 1];
const hListReveal = revealedContainer.querySelector('.ai-hints-hint-list');
const oListReveal = revealedContainer.querySelector('.ai-hints-list');

console.log("Hints display style:", hListReveal.style.display);
console.log("Options display style:", oListReveal.style.display);

if (hListReveal.style.display !== 'block') throw new Error("Hints should be automatically revealed");
if (oListReveal.style.display === 'block') throw new Error("Options should remain hidden");

console.log("\n--- TEST 5: SETUP WITH NULL DATA CLEARS STALE JSON ---");
global.window.aiHintsCurrentCard = { id: 'card_stale_test', ord: 0 };
global.window.aiHintsUiConfig = { is_generating: false };
const staleTest = createMockDOM({ isAddonActive: true, hasData: true });
eval(scriptContent);
window.aiHintsSetup({ id: 'empty_card_after_clear', ord: 0 }, null);
const staleRendered = staleTest.getRendered().filter(el => el.className === 'ai-hints-container');
const staleLabels = staleRendered[staleRendered.length - 1].querySelector('.ai-hints-btn-box').querySelectorAll('button').map(b => b.textContent);
console.log("Buttons found after null setup:", staleLabels.join(', '));
if (staleTest.getJsonBlocks().length !== 0) throw new Error("Stale JSON blocks should be removed");
if (!staleLabels.includes("Generate AI Hints")) throw new Error("Empty card should show Generate AI Hints");
if (staleLabels.includes("Regenerate")) throw new Error("Empty card should not show stale Regenerate state");

console.log("\nALL JS TESTS PASSED.");
process.exit(0);
