
const fs = require('fs');
const path = require('path');

/**
 * Mock DOM Environment Factory
 */
function createMockDOM(env) {
    const { isAddonActive, hasData } = env;
    
    let renderedBlocks = [];
    let jsonBlocks = [];
    let staticContainers = [];
    function addJsonBlock(data = { hints: ["H1"], options: ["O1"] }, attrs = {}) {
        const jsonBlock = {
            textContent: JSON.stringify(data),
            dataset: {},
            attrs,
            classList: {
                contains: (cls) => cls === 'ai-hints-json'
            },
            getAttribute: (name) => attrs[name] || null,
            parentNode: { insertBefore: (n, r) => renderedBlocks.push(n) },
            remove: () => { jsonBlocks = jsonBlocks.filter(item => item !== jsonBlock); }
        };
        jsonBlocks.push(jsonBlock);
        return jsonBlock;
    }
    function makeElement(tag) {
        const attrs = {};
        const el = {
            tagName: tag.toUpperCase(),
            className: '',
            classList: {
                add: (cls) => {
                    if (!el.className.split(/\s+/).includes(cls)) {
                        el.className = `${el.className} ${cls}`.trim();
                    }
                },
                remove: (cls) => {
                    el.className = el.className.split(/\s+/).filter(item => item && item !== cls).join(' ');
                },
                contains: (cls) => el.className.split(/\s+/).includes(cls)
            },
            textContent: '',
            innerHTML: '',
            style: {},
            dataset: {},
            attrs,
            children: [],
            setAttribute: (name, value) => {
                attrs[name] = String(value);
                if (name === 'class') el.className = String(value);
            },
            getAttribute: (name) => attrs[name] || null,
            appendChild: (child) => {
                child.parentNode = el;
                el.children.push(child);
            },
            querySelector: (sel) => {
                const cleanSel = sel.replace('.', '');
                let found = null;
                const search = (node) => {
                    if (found) return;
                        if (node.tagName === cleanSel.toUpperCase()) { found = node; return; }
                    if (node.className && node.className.includes(cleanSel)) { found = node; return; }
                    if (node.children) node.children.forEach(search);
                };
                search(el);
                return found;
            },
            querySelectorAll: (sel) => {
                const cleanSel = sel.replace('.', '');
                const found = [];
                const search = (node) => {
                    if (node !== el) {
                        if (node.tagName === cleanSel.toUpperCase()) found.push(node);
                        else if (node.className && node.className.includes(cleanSel)) found.push(node);
                    }
                    if (node.children) node.children.forEach(search);
                };
                search(el);
                return found;
            },
            remove: () => {
                renderedBlocks = renderedBlocks.filter(item => item !== el);
                staticContainers = staticContainers.filter(item => item !== el);
                jsonBlocks = jsonBlocks.filter(item => item !== el);
                if (el.parentNode && el.parentNode.children) {
                    el.parentNode.children = el.parentNode.children.filter(item => item !== el);
                }
            }
        };
        return el;
    }
    function addStaticContainer(attrs = {}) {
        const container = makeElement('div');
        container.className = 'ai-hints-container';
        Object.entries(attrs).forEach(([name, value]) => container.setAttribute(name, value));
        staticContainers.push(container);
        return container;
    }
    if (hasData) addJsonBlock();
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
            if (selector === '.ai-hints-container' || selector === '.ai-hints-container-rendered') {
                return renderedBlocks.concat(staticContainers).filter(el => el.className && (el.className.includes('ai-hints-container') || el.className.includes('ai-hints-container-rendered')));
            }
            if (selector === '.ai-hints-json') return jsonBlocks;
            if (selector === '.ai-hints-btn') {
                const btns = [];
                const search = (el) => {
                    if (el.tagName === 'BUTTON' || (el.className && el.className.includes('ai-hints-btn'))) btns.push(el);
                    if (el.children) el.children.forEach(search);
                };
                renderedBlocks.forEach(search);
                return btns;
            }
            return [];
        },
        querySelector: (selector) => {
            if (selector === '.ai-hints-container' || selector === '.ai-hints-container-rendered') {
                return renderedBlocks.concat(staticContainers).find(el => el.className && (el.className.includes('ai-hints-container') || el.className.includes('ai-hints-container-rendered'))) || null;
            }
            return null;
        },
        createElement: makeElement,
        readyState: 'complete',
        addEventListener: () => {}
    };

    if (!global.window) global.window = {};
    global.window = {
        ...global.window,
        aiHintsUiConfig: isAddonActive ? (global.window.aiHintsUiConfig || { is_generating: false }) : null,
        aiHintsMobileConfig: !isAddonActive ? { useEmojis: true, showExtraButtons: true } : null,
        aiHintsLastSetupKey: undefined,
        aiHintsRetryState: undefined,
        focus: () => {}
    };

    if (isAddonActive) {
        global.pycmd = (cmd) => console.log(`[MOCK PYCMD] Executing: ${cmd}`);
    } else {
        delete global.pycmd;
    }

    return {
        getRendered: () => renderedBlocks,
        getJsonBlocks: () => jsonBlocks,
        addJsonBlock,
        addStaticContainer
    };
}

const scriptPath = path.join(__dirname, '..', 'addon', 'web', 'template.js');
const scriptContent = fs.readFileSync(scriptPath, 'utf8');

console.log("--- TEST 1: DESKTOP MODE (Addon Active) ---");
const desktop = createMockDOM({ isAddonActive: true, hasData: true });
eval(scriptContent);
const desktopContainer = desktop.getRendered().find(el => el.className && el.className.includes('ai-hints-container'));
const desktopBtns = desktopContainer.querySelector('.ai-hints-btn-box').querySelectorAll('button');
const desktopLabels = desktopBtns.map(b => b.textContent);
console.log("Buttons found:", desktopLabels.join(', '));
if (!desktopLabels.includes("Regenerate")) throw new Error("Missing Regenerate button on Desktop");
if (!desktopLabels.includes("Clear")) throw new Error("Missing Clear button on Desktop");

console.log("\n--- TEST 2: MOBILE MODE (Standalone) ---");
const mobile = createMockDOM({ isAddonActive: false, hasData: true });
eval(scriptContent);
const mobileContainer = mobile.getRendered().find(el => el.className && el.className.includes('ai-hints-container'));
const mobileBtns = mobileContainer.querySelector('.ai-hints-btn-box').querySelectorAll('button');
const mobileLabels = mobileBtns.map(b => b.textContent);
console.log("Buttons found:", mobileLabels.join(', '));
if (mobileLabels.includes("Regenerate") || mobileLabels.includes("Generate AI Hints")) 
    throw new Error("Generate button should NOT appear on Mobile");
if (mobileLabels.includes("🗑️") || mobileLabels.includes("Clear"))
    throw new Error("Clear button should NOT appear on Mobile");
if (mobileLabels.includes("💡 Hints")) console.log("Emoji support verified");

console.log("\n--- TEST 3: NO DATA (Desktop) ---");
const noData = createMockDOM({ isAddonActive: true, hasData: false });
eval(scriptContent);
const allRendered = noData.getRendered();
const noDataContainer = allRendered.find(el => el.className && el.className.includes('ai-hints-container'));
if (!noDataContainer) throw new Error("Container not found in Desktop mode with no data");
const noDataBtns = noDataContainer.querySelector('.ai-hints-btn-box').querySelectorAll('button');
console.log("Buttons found:", noDataBtns.map(b => b.textContent).join(', '));
if (noDataBtns[0].textContent !== "Generate AI Hints") throw new Error("Should show 'Generate' when no data");
window.aiHintsSetGenerating(true);
const generatingBtns = noData.getRendered().find(el => el.className && el.className.includes('ai-hints-container')).querySelector('.ai-hints-btn-box').querySelectorAll('button');
if (generatingBtns[0].textContent !== "✨ Generating...") throw new Error("Auto-generation should animate the Generate button");
if (!generatingBtns[0].disabled) throw new Error("Generating button should be disabled during auto-generation");
window.aiHintsUpdateData({ hints: ["Done"], options: ["Option"] });
const doneContainer = noData.getRendered().find(el => el.className && el.className.includes('ai-hints-container'));
const doneBtns = doneContainer.querySelector('.ai-hints-btn-box').querySelectorAll('button');
console.log("TEST 3 Buttons found after update:", doneBtns.map(b => b.textContent).join(', '));
const doneBtn = doneBtns[0];
if (doneBtn.textContent === "✨ Generating...") throw new Error("Generating animation should stop after successful update");
if (doneBtn.disabled) throw new Error("Generate button should be enabled after successful update");

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
window.aiHintsUpdateData({ hints: ["Hint revealed!"], options: ["Option hidden"] }, true);

// Find the last container (the one created by aiHintsUpdateData)
const allRenders = revealTest.getRendered();
const revealedContainer = allRenders[allRenders.length - 1];
const hListReveal = revealedContainer.querySelector('.ai-hints-hint-list');
const oListReveal = revealedContainer.querySelector('.ai-hints-list');

console.log("Hints display style:", hListReveal.parentNode.style.display);
console.log("Options display style:", oListReveal.parentNode.style.display);

if (hListReveal.parentNode.style.display !== 'block') throw new Error("Hints should be automatically revealed");
if (oListReveal.parentNode.style.display === 'block') throw new Error("Options should remain hidden");

console.log("\n--- TEST 6: DUPLICATE SETUP IS IDEMPOTENT ---");
global.window.aiHintsUiConfig = { is_generating: false };
const idempotentTest = createMockDOM({ isAddonActive: true, hasData: false });
eval(scriptContent);
const setupCard = { id: 'stable_card', ord: 0 };
const setupHints = { hints: ["Stable"], options: ["Option"] };
window.aiHintsSetup(setupCard, setupHints);
const firstSetupCount = idempotentTest.getRendered().filter(el => el.className && el.className.includes('ai-hints-container')).length;
window.aiHintsSetup(setupCard, setupHints);
const secondSetupCount = idempotentTest.getRendered().filter(el => el.className && el.className.includes('ai-hints-container')).length;
if (secondSetupCount !== firstSetupCount) throw new Error("Duplicate setup should not rebuild rendered containers");

console.log("\n--- TEST 7: STALE SCOPED JSON IS IGNORED ---");
global.window.aiHintsCurrentCard = { id: 'current_card', ord: 0 };
global.window.aiHintsUiConfig = { is_generating: false };
const scopedStaleTest = createMockDOM({ isAddonActive: true, hasData: false });
scopedStaleTest.addJsonBlock(
    { hints: ["Old card"], options: ["Old option"] },
    { 'data-ai-hints-card-id': 'previous_card', 'data-ai-hints-card-ord': '0' }
);
eval(scriptContent);
const scopedStaleLabels = scopedStaleTest.getRendered().find(el => el.className && el.className.includes('ai-hints-container')).querySelector('.ai-hints-btn-box').querySelectorAll('button').map(b => b.textContent);
if (scopedStaleTest.getJsonBlocks().length !== 0) throw new Error("Stale scoped JSON block should be removed");
if (!scopedStaleLabels.includes("Generate AI Hints")) throw new Error("Current empty card should not render previous card data");
if (scopedStaleLabels.includes("Regenerate")) throw new Error("Previous card data should not make current card look generated");

console.log("\n--- TEST 8: STALE HTML CONTAINER IS CLEARED DURING CARD TRANSITION ---");
global.window.aiHintsCurrentCard = { id: 'new_card', ord: 0 };
global.window.aiHintsUiConfig = { is_generating: false };
const transitionTest = createMockDOM({ isAddonActive: true, hasData: false });
transitionTest.addStaticContainer({ 'data-ai-hints-card-id': 'old_card', 'data-ai-hints-card-ord': '0' });
transitionTest.addJsonBlock(
    { hints: ["New card"], options: ["New option"] },
    { 'data-ai-hints-card-id': 'new_card', 'data-ai-hints-card-ord': '0' }
);
eval(scriptContent);
const transitionContainers = transitionTest.getRendered().filter(el => el.className && el.className.includes('ai-hints-container'));
if (transitionContainers.length !== 1) throw new Error("Exactly one current-card container should be rendered");
const transitionLabels = transitionContainers[0].querySelector('.ai-hints-btn-box').querySelectorAll('button').map(b => b.textContent);
if (!transitionLabels.includes("Regenerate")) throw new Error("Current card data should render after stale HTML is cleared");

console.log("\n--- TEST 9: DUPLICATE CURRENT JSON RENDERS ONE CONTAINER ---");
global.window.aiHintsCurrentCard = { id: 'dup_card', ord: 0 };
global.window.aiHintsUiConfig = { is_generating: false };
const duplicateDataTest = createMockDOM({ isAddonActive: true, hasData: false });
duplicateDataTest.addJsonBlock(
    { hints: ["First"], options: ["A"] },
    { 'data-ai-hints-card-id': 'dup_card', 'data-ai-hints-card-ord': '0' }
);
duplicateDataTest.addJsonBlock(
    { hints: ["Second"], options: ["B"] },
    { 'data-ai-hints-card-id': 'dup_card', 'data-ai-hints-card-ord': '0' }
);
eval(scriptContent);
const duplicateContainers = duplicateDataTest.getRendered().filter(el => el.className && el.className.includes('ai-hints-container'));
if (duplicateContainers.length !== 1) throw new Error("Duplicate current-card JSON blocks should still render one container");

console.log("\n--- TEST 10: UNSCOPED KEYED JSON FOR SECOND FIELD IS DETECTED ---");
global.window.aiHintsCurrentCard = { id: 'keyed_card', ord: 1 };
global.window.aiHintsUiConfig = { is_generating: false };
const unscopedKeyedTest = createMockDOM({ isAddonActive: true, hasData: false });
unscopedKeyedTest.addJsonBlock({
    c1: { hints: ["First ord"], options: ["First option"] },
    c2: { hints: ["Second field hint"], options: ["Second field option"] }
});
eval(scriptContent);
const keyedContainer = unscopedKeyedTest.getRendered().find(el => el.className && el.className.includes('ai-hints-container'));
const keyedLabels = keyedContainer.querySelector('.ai-hints-btn-box').querySelectorAll('button').map(b => b.textContent);
if (!keyedLabels.includes("Regenerate")) throw new Error("Unscoped keyed c2 JSON should render for card ord 1");
const keyedHints = keyedContainer.querySelector('.ai-hints-hint-list').querySelectorAll('li').map(li => li.innerHTML || li.textContent);
if (!keyedHints.includes("Second field hint")) throw new Error("Card ord 1 should read c2 data from unscoped keyed JSON");

console.log("\n--- TEST 11: UNMATCHED JSON DOES NOT RENDER EMPTY GENERATE STATE ---");
global.window.aiHintsCurrentCard = { id: 'waiting_card', ord: 0 };
global.window.aiHintsUiConfig = { is_generating: false };
const retryTest = createMockDOM({ isAddonActive: true, hasData: false });
retryTest.addJsonBlock(
    { c2: { hints: ["Other ord"], options: ["Other option"] } }
);
eval(scriptContent);
const retryContainers = retryTest.getRendered().filter(el => el.className && el.className.includes('ai-hints-container'));
if (retryContainers.length !== 0) throw new Error("Unmatched pending JSON should wait instead of showing Generate");

console.log("\n--- TEST 12: NULL FRONT SETUP DOES NOT ERASE CURRENT DATA CONTAINER ---");
global.window.aiHintsCurrentCard = { id: 'front_card', ord: 0 };
global.window.aiHintsUiConfig = { is_generating: false };
const frontSetupTest = createMockDOM({ isAddonActive: true, hasData: false });
eval(scriptContent);
window.aiHintsSetup({ id: 'front_card', ord: 0 }, { hints: ["Front data"], options: ["Front option"] });
const frontCountBefore = frontSetupTest.getRendered().filter(el => el.className && el.className.includes('ai-hints-container')).length;
window.aiHintsSetup({ id: 'front_card', ord: 0 }, null);
const frontContainers = frontSetupTest.getRendered().filter(el => el.className && el.className.includes('ai-hints-container'));
if (frontContainers.length !== frontCountBefore) throw new Error("Null setup should not remove current data container");
const frontLabels = frontContainers[0].querySelector('.ai-hints-btn-box').querySelectorAll('button').map(b => b.textContent);
if (!frontLabels.includes("Regenerate")) throw new Error("Current data container should stay in Regenerate state after null setup");

console.log("\nALL JS TESTS PASSED."); process.exit(0);
