
const fs = require('fs');
const path = require('path');

/**
 * Mock DOM Environment Factory
 */
function createMockDOM(env) {
    const { isAddonActive, hasData, isAnswerSide, clozes, clozeLayout } = env;
    
    let renderedBlocks = [];
    let jsonBlocks = [];
    let staticContainers = [];

    function relinkChildren(parent) {
        const children = parent.children || [];
        parent.childNodes = children;
        children.forEach((child, index) => {
            child.parentNode = parent;
            child.previousSibling = children[index - 1] || null;
            child.nextSibling = children[index + 1] || null;
        });
    }

    function trackRenderedNode(node) {
        if (node && node.className && node.className.includes('ai-hints-container') && !renderedBlocks.includes(node)) {
            renderedBlocks.push(node);
        }
    }

    function makeText(text) {
        return {
            nodeType: 3,
            textContent: text,
            parentNode: null,
            previousSibling: null,
            nextSibling: null
        };
    }

    function makeElement(tag) {
        const attrs = {};
        const el = {
            nodeType: 1,
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
            childNodes: [],
            parentNode: null,
            previousSibling: null,
            nextSibling: null,
            setAttribute: (name, value) => {
                attrs[name] = String(value);
                if (name === 'class') el.className = String(value);
            },
            getAttribute: (name) => attrs[name] || null,
            addEventListener: () => {},
            removeEventListener: () => {},
            appendChild: (child) => {
                child.parentNode = el;
                el.children.push(child);
                relinkChildren(el);
                trackRenderedNode(child);
            },
            insertBefore: (child, ref) => {
                child.parentNode = el;
                const idx = ref ? el.children.indexOf(ref) : -1;
                if (idx >= 0) el.children.splice(idx, 0, child);
                else el.children.push(child);
                relinkChildren(el);
                trackRenderedNode(child);
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
                    relinkChildren(el.parentNode);
                }
            }
        };
        return el;
    }

    const bodyEl = makeElement('body');

    function addJsonBlock(data = { hints: ["H1"], options: ["O1"] }, attrs = {}) {
        const jsonBlock = makeElement('div');
        jsonBlock.className = 'ai-hints-json';
        jsonBlock.textContent = JSON.stringify(data);
        jsonBlock.attrs = attrs;
        jsonBlock.getAttribute = (name) => attrs[name] || null;
        Object.entries(attrs).forEach(([name, value]) => jsonBlock.setAttribute(name, value));
        jsonBlock.remove = () => {
            jsonBlocks = jsonBlocks.filter(item => item !== jsonBlock);
            if (jsonBlock.parentNode && jsonBlock.parentNode.children) {
                jsonBlock.parentNode.children = jsonBlock.parentNode.children.filter(item => item !== jsonBlock);
                relinkChildren(jsonBlock.parentNode);
            }
        };
        jsonBlocks.push(jsonBlock);
        bodyEl.appendChild(jsonBlock);
        return jsonBlock;
    }

    if (clozeLayout) {
        bodyEl.appendChild(makeText("Prompt before "));
        const cloze = makeElement('span');
        cloze.className = 'cloze';
        cloze.textContent = (clozes && clozes[0]) || "Revealed answer";
        bodyEl.appendChild(cloze);
        bodyEl.appendChild(makeText(" prompt after"));
        bodyEl.appendChild(makeElement('br'));
        bodyEl.appendChild(makeText("Extra field"));
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
        body: bodyEl,
        getElementById: (id) => {
            if (id === 'qa') return bodyEl;
            return null;
        },
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
            if (selector === '.cloze') {
                const realClozes = bodyEl.querySelectorAll('.cloze');
                if (realClozes.length) return realClozes;
                return (clozes || []).map(txt => ({ textContent: txt, className: 'cloze' }));
            }
            return [];
        },
        querySelector: (selector) => {
            if (selector === '.answer' && isAnswerSide) return { className: 'answer' };
            if (selector === 'hr') return bodyEl.querySelector('hr');
            if (selector === '.ai-hints-container' || selector === '.ai-hints-container-rendered') {
                return renderedBlocks.concat(staticContainers).find(el => el.className && (el.className.includes('ai-hints-container') || el.className.includes('ai-hints-container-rendered'))) || null;
            }
            if (selector === 'ai-hints') return bodyEl.querySelector('ai-hints');
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
        addEventListener: () => {},
        removeEventListener: () => {},
        focus: () => {}
    };

    if (isAddonActive) {
        global.pycmd = (cmd) => console.log(`[MOCK PYCMD] Executing: ${cmd}`);
    } else {
        delete global.pycmd;
    }

    return {
        getRendered: () => renderedBlocks,
        getBodyChildren: () => bodyEl.children,
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

console.log("\n--- TEST 11B: EXHAUSTED RETRY FALLS BACK TO BUTTONS ---");
global.window.aiHintsCurrentCard = { id: 'waiting_done_card', ord: 0 };
global.window.aiHintsUiConfig = { is_generating: false };
const exhaustedRetryTest = createMockDOM({ isAddonActive: true, hasData: false });
global.window.aiHintsRetryState = { waiting_done_card_0: 8 };
exhaustedRetryTest.addJsonBlock(
    { c2: { hints: ["Other ord"], options: ["Other option"] } }
);
eval(scriptContent);
const exhaustedContainer = exhaustedRetryTest.getRendered().find(el => el.className && el.className.includes('ai-hints-container'));
if (!exhaustedContainer) throw new Error("Exhausted retry should render fallback buttons");
const exhaustedLabels = exhaustedContainer.querySelector('.ai-hints-btn-box').querySelectorAll('button').map(b => b.textContent);
if (!exhaustedLabels.includes("Generate AI Hints")) throw new Error("Exhausted retry should show Generate fallback");

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

console.log("\n--- TEST 13: BACK SIDE CORRECT OPTION HIGHLIGHT NORMALIZES MATH AND ENTITIES ---");
global.window.aiHintsCurrentCard = { id: 'answer_card', ord: 0 };
global.window.aiHintsUiConfig = { is_generating: false, is_answer_side: true };
const highlightTest = createMockDOM({ isAddonActive: true, hasData: false, isAnswerSide: true });
highlightTest.addJsonBlock(
    {
        hints: ["Compare the expressions"],
        options: ["\\( x < y \\)", "$z$"],
        correct_answer: "$x &lt; y$"
    },
    { 'data-ai-hints-card-id': 'answer_card', 'data-ai-hints-card-ord': '0' }
);
eval(scriptContent);
const highlightContainer = highlightTest.getRendered().find(el => el.className && el.className.includes('ai-hints-container'));
const highlightedItems = highlightContainer.querySelector('.ai-hints-list').querySelectorAll('li').filter(li => li.className === 'ai-hints-correct');
if (highlightedItems.length !== 1) throw new Error("Exactly one correct option should be highlighted on the back side");
if (highlightedItems[0].innerHTML !== "\\( x &lt; y \\)") throw new Error("The normalized matching option should be highlighted");

console.log("\n--- TEST 14: FIRST OPTION CORRECT MARKER SURVIVES SHUFFLE ---");
global.window.aiHintsCurrentCard = { id: 'shuffle_card', ord: 0 };
global.window.aiHintsUiConfig = { is_generating: false, is_answer_side: true };
const shuffleHighlightTest = createMockDOM({ isAddonActive: true, hasData: false, isAnswerSide: true });
shuffleHighlightTest.addJsonBlock(
    {
        hints: ["The first option is the answer before shuffle"],
        options: ["Correct", "Distractor A", "Distractor B", "Distractor C"],
        correct_answer: "Correct"
    },
    { 'data-ai-hints-card-id': 'shuffle_card', 'data-ai-hints-card-ord': '0' }
);
eval(scriptContent);
const shuffleContainer = shuffleHighlightTest.getRendered().find(el => el.className && el.className.includes('ai-hints-container'));
const shuffledItems = shuffleContainer.querySelector('.ai-hints-list').querySelectorAll('li');
const shuffledHighlighted = shuffledItems.filter(li => li.className === 'ai-hints-correct');
if (shuffledHighlighted.length !== 1) throw new Error("Exactly one shuffled option should keep the correct class");
if (shuffledHighlighted[0].innerHTML !== "Correct") throw new Error("The pre-shuffle first option should remain highlighted after shuffle");

console.log("\n--- TEST 15: CLOZE FRONT SIDE DETECTION (contains [...]) ---");
global.window.aiHintsCurrentCard = { id: 'cloze_front', ord: 0 };
global.window.aiHintsUiConfig = { is_generating: false };
const clozeFrontTest = createMockDOM({ isAddonActive: true, hasData: false, isAnswerSide: false, clozes: ["[...] under Article 213"] });
clozeFrontTest.addJsonBlock(
    {
        hints: ["Test hint"],
        options: ["Opt A", "Opt B"],
        correct_answer: "Opt A"
    },
    { 'data-ai-hints-card-id': 'cloze_front', 'data-ai-hints-card-ord': '0' }
);
eval(scriptContent);
const clozeFrontContainer = clozeFrontTest.getRendered().find(el => el.className && el.className.includes('ai-hints-container'));
const clozeFrontHighlighted = clozeFrontContainer.querySelector('.ai-hints-list').querySelectorAll('li').filter(li => li.className === 'ai-hints-correct');
if (clozeFrontHighlighted.length !== 0) throw new Error("No option should be highlighted on the front side of a cloze card");

console.log("\n--- TEST 16: CLOZE BACK SIDE DETECTION (does NOT contain [...]) ---");
global.window.aiHintsCurrentCard = { id: 'cloze_back', ord: 0 };
global.window.aiHintsUiConfig = { is_generating: false };
const clozeBackTest = createMockDOM({ isAddonActive: true, hasData: false, isAnswerSide: false, clozes: ["The Governor of a state under Article 213"] });
clozeBackTest.addJsonBlock(
    {
        hints: ["Test hint"],
        options: ["The Governor of a state", "Opt B"],
        correct_answer: "The Governor of a state"
    },
    { 'data-ai-hints-card-id': 'cloze_back', 'data-ai-hints-card-ord': '0' }
);
eval(scriptContent);
const clozeBackContainer = clozeBackTest.getRendered().find(el => el.className && el.className.includes('ai-hints-container'));
const clozeBackHighlighted = clozeBackContainer.querySelector('.ai-hints-list').querySelectorAll('li').filter(li => li.className === 'ai-hints-correct');
if (clozeBackHighlighted.length !== 1) throw new Error("The correct option should be highlighted on the back side of a cloze card via the cloze text heuristic");
if (clozeBackHighlighted[0].innerHTML !== "The Governor of a state") throw new Error("The matching option should be highlighted");

console.log("\n--- TEST 17: CLOZE BACK SIDE PLACEMENT BEFORE EXTRA WITHOUT HR ---");
global.window.aiHintsCurrentCard = { id: 'cloze_place', ord: 0 };
global.window.aiHintsUiConfig = { is_generating: false, answer_display_position: 'between' };
const clozePlacementTest = createMockDOM({
    isAddonActive: true,
    hasData: false,
    isAnswerSide: false,
    clozes: ["The Governor of a state"],
    clozeLayout: true
});
clozePlacementTest.addJsonBlock(
    {
        hints: ["Test hint"],
        options: ["The Governor of a state", "Opt B"],
        correct_answer: "The Governor of a state"
    },
    { 'data-ai-hints-card-id': 'cloze_place', 'data-ai-hints-card-ord': '0' }
);
eval(scriptContent);
const clozePlacementContainer = clozePlacementTest.getRendered().find(el => el.className && el.className.includes('ai-hints-container'));
const clozePlacementChildren = clozePlacementTest.getBodyChildren();
const clozePlacementIndex = clozePlacementChildren.indexOf(clozePlacementContainer);
const clozeExtraIndex = clozePlacementChildren.findIndex(node => node.textContent === "Extra field");
const clozeJsonIndex = clozePlacementChildren.findIndex(node => node.className === "ai-hints-json");
if (clozePlacementIndex < 0) throw new Error("Cloze placement test should render a container");
if (!(clozePlacementIndex < clozeExtraIndex)) throw new Error("Cloze answer controls should render before Extra when no HR exists");
if (!(clozePlacementIndex < clozeJsonIndex)) throw new Error("Cloze answer controls should not be placed after trailing fallback JSON");

console.log("\n--- TEST 18: CLOZE FRONT SIDE DETECTION WITH CUSTOM HINTS (e.g. [case]) ---");
global.window.aiHintsCurrentCard = { id: 'cloze_front_hint', ord: 0 };
global.window.aiHintsUiConfig = { is_generating: false };
const clozeFrontHintTest = createMockDOM({ isAddonActive: true, hasData: false, isAnswerSide: false, clozes: ["[case]"] });
clozeFrontHintTest.addJsonBlock(
    {
        hints: ["Test hint"],
        options: ["Shankari Prasad", "Golak Nath"],
        correct_answer: "Shankari Prasad"
    },
    { 'data-ai-hints-card-id': 'cloze_front_hint', 'data-ai-hints-card-ord': '0' }
);
eval(scriptContent);
const clozeFrontHintContainer = clozeFrontHintTest.getRendered().find(el => el.className && el.className.includes('ai-hints-container'));
const clozeFrontHintHighlighted = clozeFrontHintContainer.querySelector('.ai-hints-list').querySelectorAll('li').filter(li => li.className === 'ai-hints-correct');
if (clozeFrontHintHighlighted.length !== 0) throw new Error("No option should be highlighted on the front side of a cloze card containing a custom hint like [case]");

console.log("\n--- TEST 19: HTML CODE TAGS ARE ESCAPED IN OPTIONS ---");
global.window.aiHintsCurrentCard = { id: 'html_escape_card', ord: 0 };
global.window.aiHintsUiConfig = { is_generating: false, is_answer_side: true };
const htmlEscapeTest = createMockDOM({ isAddonActive: true, hasData: false, isAnswerSide: true });
htmlEscapeTest.addJsonBlock(
    {
        hints: ["Test html"],
        options: ["<a href=\"url\">My Page</a>", "<b>Bold Text</b>"],
        correct_answer: "<a href=\"url\">My Page</a>"
    },
    { 'data-ai-hints-card-id': 'html_escape_card', 'data-ai-hints-card-ord': '0' }
);
eval(scriptContent);
const htmlEscapeContainer = htmlEscapeTest.getRendered().find(el => el.className && el.className.includes('ai-hints-container'));
const htmlEscapeItems = htmlEscapeContainer.querySelector('.ai-hints-list').querySelectorAll('li');
const hasEscapedLink = htmlEscapeItems.some(item => item.innerHTML.indexOf('&lt;a') !== -1);
const hasPreservedBold = htmlEscapeItems.some(item => item.innerHTML.indexOf('<b>Bold') !== -1);
if (!hasEscapedLink) throw new Error("HTML tags in options should be escaped to display as text");
if (!hasPreservedBold) throw new Error("Safe formatting tags should be preserved in options");

console.log("\n--- TEST 20: ONLY THE CORRECT HTML CODE TAG OPTION IS HIGHLIGHTED ---");
global.window.aiHintsCurrentCard = { id: 'html_correct_card', ord: 0 };
global.window.aiHintsUiConfig = { is_generating: false, is_answer_side: true };
const htmlCorrectTest = createMockDOM({ isAddonActive: true, hasData: false, isAnswerSide: true });
htmlCorrectTest.addJsonBlock(
    {
        hints: ["Test HTML"],
        options: [
            "<a href=\"url\">link text</a>",
            "<a src=\"url\">link text</a>",
            "<link href=\"url\">link text</link>",
            "<url href=\"link text\">link text</url>"
        ],
        correct_answer: "<a href=\"url\">link text</a>"
    },
    { 'data-ai-hints-card-id': 'html_correct_card', 'data-ai-hints-card-ord': '0' }
);
eval(scriptContent);
const htmlCorrectContainer = htmlCorrectTest.getRendered().find(el => el.className && el.className.includes('ai-hints-container'));
const htmlCorrectItems = htmlCorrectContainer.querySelector('.ai-hints-list').querySelectorAll('li');
const highlightedCorrect = htmlCorrectItems.filter(li => li.className === 'ai-hints-correct');
if (highlightedCorrect.length !== 1) throw new Error("Exactly one correct HTML option should be highlighted");
if (highlightedCorrect[0].innerHTML.indexOf('&lt;a href=') === -1) throw new Error("The highlighted option should be the correct escaped anchor tag");

console.log("\nALL JS TESTS PASSED."); process.exit(0);
