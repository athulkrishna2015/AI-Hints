(function() {
    const Persistence = {
        saveState: function(cardId, state) {
            if (!cardId || cardId.startsWith('_')) return;
            try {
                sessionStorage.setItem('ai_hints_state_' + cardId, JSON.stringify(state));
            } catch (e) {}
        },
        getState: function(cardId) {
            if (!cardId || cardId.startsWith('_')) return null;
            try {
                const raw = sessionStorage.getItem('ai_hints_state_' + cardId);
                return raw ? JSON.parse(raw) : null;
            } catch (e) { return null; }
        },
        saveData: function(cardId, data) {
            if (!cardId || cardId.startsWith('_')) return;
            try {
                sessionStorage.setItem('ai_hints_data_' + cardId, JSON.stringify(data));
            } catch (e) {}
        },
        getData: function(cardId) {
            if (!cardId || cardId.startsWith('_')) return null;
            try {
                const raw = sessionStorage.getItem('ai_hints_data_' + cardId);
                return raw ? JSON.parse(raw) : null;
            } catch (e) { return null; }
        }
    };

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

        const cardBody = document.getElementById('qa');

        // Priority 1: Scoped match inside QA
        const scopedInside = blocks.find(function(block) {
            return cardBody && cardBody.contains(block) && hasCardScope(block) && matchesCurrentCard(block);
        });
        if (scopedInside) return scopedInside;

        // Priority 2: Scoped match anywhere
        const scopedMatch = blocks.find(function(block) {
            return hasCardScope(block) && matchesCurrentCard(block);
        });
        if (scopedMatch) return scopedMatch;

        // Priority 3: Legacy match inside QA
        const legacyInside = blocks.find(function(block) {
            return cardBody && cardBody.contains(block) && !hasCardScope(block);
        });
        if (legacyInside) return legacyInside;

        // Priority 4: Legacy match anywhere
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
        ['aiHintsAddonId', 'showHints', 'showOptions', 'aiHintsCardId', 'aiHintsCardOrd'].forEach(function(key) {
            if (source.dataset[key] != null) {
                target.dataset[key] = source.dataset[key];
            }
        });
    }

    function applyCurrentCardAttrs(target) {
        const current = currentCard();
        const currentId = current.id == null ? '' : String(current.id);
        if (currentId) {
            target.dataset.aiHintsCardId = currentId;
        }
        if (current.ord != null) {
            target.dataset.aiHintsCardOrd = String(current.ord);
        }
    }

    function applyAddonAttrs(target) {
        target.dataset.aiHintsAddonId = '2119980872';
    }

    function setButtonEnabled(button, enabled) {
        button.disabled = !enabled;
        button.setAttribute('aria-disabled', enabled ? 'false' : 'true');
    }

    function isEscaped(text, index) {
        let slashes = 0;
        for (let i = index - 1; i >= 0 && text[i] === '\\'; i--) {
            slashes++;
        }
        return slashes % 2 === 1;
    }

    function findMatchingParen(text, start) {
        let depth = 0;
        for (let i = start; i < text.length; i++) {
            if (isEscaped(text, i)) {
                continue;
            }
            if (text[i] === '(') {
                depth++;
            } else if (text[i] === ')') {
                depth--;
                if (depth === 0) {
                    return i;
                }
            }
        }
        return -1;
    }

    function findNextEscapedMathClose(text, start) {
        let depth = 0;
        for (let i = start; i < text.length - 1; i++) {
            if (text.startsWith('\\(', i)) {
                depth++;
                i++;
                continue;
            }
            if (text.startsWith('\\)', i)) {
                if (depth === 0) {
                    return i;
                }
                depth--;
                i++;
            }
        }
        return -1;
    }

    function findNextEscapedDisplayClose(text, start) {
        let depth = 0;
        for (let i = start; i < text.length - 1; i++) {
            if (text.startsWith('\\[', i)) {
                depth++;
                i++;
                continue;
            }
            if (text.startsWith('\\]', i)) {
                if (depth === 0) {
                    return i;
                }
                depth--;
                i++;
            }
        }
        return -1;
    }

    function findNextUnescapedCloseParen(text, start) {
        for (let i = start; i < text.length; i++) {
            if (text[i] === ')' && !isEscaped(text, i)) {
                return i;
            }
        }
        return -1;
    }

    function findNextUnescapedCloseBracket(text, start) {
        for (let i = start; i < text.length; i++) {
            if (text[i] === ']' && !isEscaped(text, i)) {
                return i;
            }
        }
        return -1;
    }

    function looksLikeMathSpan(text) {
        const stripped = String(text || '').trim();
        if (!stripped || stripped.length > 220) {
            return false;
        }
        return /[\\_=^{}]/.test(stripped) || /\b[A-Za-z]+\s*\([^)]*\)/.test(stripped);
    }

    function unwrapMathDelimitersInsideSpan(span) {
        return String(span || '')
            .replace(/\\\(([\s\S]*?)\\\)/g, function(match, inner) {
                return inner.trim();
            })
            .replace(/\\\[([\s\S]*?)\\\]/g, function(match, inner) {
                return inner.trim();
            });
    }

    function fixLatexSpan(span) {
        let text = String(span || '');
        const commands = [
            'exp', 'lambda', 'frac', 'left', 'right', 'sin', 'cos', 'tan',
            'sqrt', 'log', 'ln', 'lim', 'min', 'max', 'det', 'dim', 'ker',
            'approx', 'cdot', 'times', 'div', 'pm', 'mp', 'text', 'mathrm',
            'operatorname', 'partial', 'nabla', 'int', 'iint', 'iiint', 'oint',
            'sum', 'prod', 'infty', 'to', 'rightarrow', 'leftarrow',
            'leftrightarrow', 'le', 'leq', 'ge', 'geq', 'ne', 'neq', 'in',
            'notin', 'subset', 'subseteq', 'supset', 'supseteq', 'cup', 'cap',
            'forall', 'exists', 'emptyset', 'mathbb', 'mathcal', 'mathfrak',
            'vec', 'hat', 'bar', 'overline', 'underline', 'dot', 'ddot',
            'tilde', 'widehat', 'widetilde', 'begin', 'end',
            'alpha', 'beta', 'gamma', 'delta', 'epsilon', 'phi', 'theta',
            'omega', 'mu', 'nu', 'pi', 'rho', 'sigma', 'tau', 'chi', 'psi'
        ];
        const functions = ['exp', 'sin', 'cos', 'tan', 'log', 'ln', 'lim'];
        const commandAlt = commands.join('|');
        const protectedText = [];

        text = text.replace(/\\(?:text|mathrm|operatorname)\{[^{}]*\}/g, function(match) {
            protectedText.push(match);
            return '@@AI_HINTS_LATEX_TEXT_' + (protectedText.length - 1) + '@@';
        });
        text = unwrapMathDelimitersInsideSpan(text);
        text = normalizeLatexOperators(text);

        text = text.replace(new RegExp('\\\\\\\\(?=(?:' + commandAlt + ')\\b)', 'g'), '\\');
        functions.forEach(function(fn) {
            text = text.replace(new RegExp('\\\\' + fn + 'left(?=\\s*\\()', 'g'), '\\' + fn + '\\left');
            text = text.replace(new RegExp('(^|[^\\\\A-Za-z])' + fn + 'left(?=\\s*\\()', 'g'), function(match, prefix) {
                return prefix + '\\' + fn + '\\left';
            });
        });
        commands.forEach(function(cmd) {
            text = text.replace(new RegExp('(^|[^\\\\A-Za-z])(' + cmd + ')(?=(_|\\b|[{}\\[\\]()+\\-=/^*,]))', 'g'), function(match, prefix, name) {
                return prefix + '\\' + name;
            });
        });
        text = normalizeParenthesizedScripts(text);
        protectedText.forEach(function(value, index) {
            text = text.replace('@@AI_HINTS_LATEX_TEXT_' + index + '@@', value);
        });
        return text;
    }

    function normalizeLatexOperators(text) {
        return text
            .replace(/(^|[^\\])<->/g, function(match, prefix) {
                return prefix + '\\leftrightarrow ';
            })
            .replace(/(^|[^\\])->/g, function(match, prefix) {
                return prefix + '\\to ';
            })
            .replace(/(^|[^\\])<=/g, function(match, prefix) {
                return prefix + '\\le ';
            })
            .replace(/(^|[^\\])>=/g, function(match, prefix) {
                return prefix + '\\ge ';
            })
            .replace(/(^|[^\\])!=/g, function(match, prefix) {
                return prefix + '\\ne ';
            });
    }

    function normalizeParenthesizedScripts(text) {
        let result = '';
        let i = 0;
        while (i < text.length) {
            if ((text[i] === '^' || text[i] === '_') && i + 1 < text.length && text[i + 1] === '(') {
                const end = findMatchingParen(text, i + 1);
                if (end !== -1) {
                    const inner = text.slice(i + 2, end).trim();
                    if (looksLikeScriptGroup(inner)) {
                        result += text[i] + '{' + inner + '}';
                        i = end + 1;
                        continue;
                    }
                }
            }
            result += text[i];
            i++;
        }
        return result;
    }

    function looksLikeScriptGroup(text) {
        const stripped = String(text || '').trim();
        return Boolean(stripped && stripped.length <= 120 && /[\\A-Za-z0-9+\-*/=^_{}<>]/.test(stripped));
    }

    function normalizePlainOpenEscapedClose(content, protectedRanges) {
        protectedRanges = protectedRanges || [];
        let result = '';
        let i = 0;
        while (i < content.length) {
            if (content[i] !== '(' || isEscaped(content, i) || indexInRanges(i, protectedRanges)) {
                result += content[i];
                i++;
                continue;
            }

            if (i > 0 && /[A-Za-z]/.test(content[i - 1])) {
                result += content[i];
                i++;
                continue;
            }

            const close = findNextEscapedMathClose(content, i + 1);
            if (close === -1) {
                result += content[i];
                i++;
                continue;
            }

            const inner = content.slice(i + 1, close);
            if (looksLikeMathSpan(unwrapMathDelimitersInsideSpan(inner))) {
                result += '\\(' + fixLatexSpan(inner) + '\\)';
                i = close + 2;
            } else {
                result += content[i];
                i++;
            }
        }
        return result;
    }

    function normalizeEscapedOpenPlainClose(content) {
        let result = '';
        let i = 0;
        while (i < content.length) {
            if (!content.startsWith('\\(', i)) {
                result += content[i];
                i++;
                continue;
            }

            if (findNextEscapedMathClose(content, i + 2) !== -1) {
                result += '\\(';
                i += 2;
                continue;
            }

            const close = findNextUnescapedCloseParen(content, i + 2);
            if (close === -1) {
                result += content[i];
                i++;
                continue;
            }

            const inner = content.slice(i + 2, close);
            if (looksLikeMathSpan(unwrapMathDelimitersInsideSpan(inner))) {
                result += '\\(' + fixLatexSpan(inner) + '\\)';
                i = close + 1;
            } else {
                result += content[i];
                i++;
            }
        }
        return result;
    }

    function normalizePlainDisplayOpenEscapedClose(content, protectedRanges) {
        protectedRanges = protectedRanges || [];
        let result = '';
        let i = 0;
        while (i < content.length) {
            if (content[i] !== '[' || isEscaped(content, i) || indexInRanges(i, protectedRanges)) {
                result += content[i];
                i++;
                continue;
            }

            if (i > 0 && /[A-Za-z0-9]/.test(content[i - 1])) {
                result += content[i];
                i++;
                continue;
            }

            const close = findNextEscapedDisplayClose(content, i + 1);
            if (close === -1) {
                result += content[i];
                i++;
                continue;
            }

            const inner = content.slice(i + 1, close);
            if (looksLikeMathSpan(unwrapMathDelimitersInsideSpan(inner))) {
                result += '\\[' + fixLatexSpan(inner) + '\\]';
                i = close + 2;
            } else {
                result += content[i];
                i++;
            }
        }
        return result;
    }

    function normalizeEscapedDisplayOpenPlainClose(content) {
        let result = '';
        let i = 0;
        while (i < content.length) {
            if (!content.startsWith('\\[', i)) {
                result += content[i];
                i++;
                continue;
            }

            if (findNextEscapedDisplayClose(content, i + 2) !== -1) {
                result += '\\[';
                i += 2;
                continue;
            }

            const close = findNextUnescapedCloseBracket(content, i + 2);
            if (close === -1) {
                result += content[i];
                i++;
                continue;
            }

            const inner = content.slice(i + 2, close);
            if (looksLikeMathSpan(unwrapMathDelimitersInsideSpan(inner))) {
                result += '\\[' + fixLatexSpan(inner) + '\\]';
                i = close + 1;
            } else {
                result += content[i];
                i++;
            }
        }
        return result;
    }

    function mathBlockRanges(content) {
        const mathBlock = /(\\\([\s\S]*?\\\)|\\\[[\s\S]*?\\\]|<anki-mathjax\b[^>]*>[\s\S]*?<\/anki-mathjax>)/gi;
        const ranges = [];
        let match;
        while ((match = mathBlock.exec(content)) !== null) {
            ranges.push([match.index, match.index + match[0].length]);
        }
        return ranges;
    }

    function indexInRanges(index, ranges) {
        return ranges.some(function(range) {
            return range[0] <= index && index < range[1];
        });
    }

    function normalizeDollarMathDelimiters(content) {
        let text = content.replace(/(^|[^\\])\$\$([\s\S]*?)(^|[^\\])\$\$/g, function(match, prefix, inner, beforeClose) {
            const span = inner + beforeClose;
            if (looksLikeMathSpan(span)) {
                return prefix + '\\[' + fixLatexSpan(span) + '\\]';
            }
            return match;
        });
        text = text.replace(/(^|[^\\])\$(?!\$)([^\n$]{1,220})(^|[^\\])\$(?!\$)/g, function(match, prefix, inner, beforeClose) {
            const span = inner + beforeClose;
            if (looksLikeMathSpan(span)) {
                return prefix + '\\(' + fixLatexSpan(span) + '\\)';
            }
            return match;
        });
        return text;
    }

    function normalizeMixedMathDelimiters(content) {
        let protectedRanges = mathBlockRanges(content);
        let text = normalizePlainDisplayOpenEscapedClose(content, protectedRanges);
        protectedRanges = mathBlockRanges(text);
        text = normalizePlainOpenEscapedClose(text, protectedRanges);
        text = normalizeEscapedDisplayOpenPlainClose(text);
        return normalizeEscapedOpenPlainClose(text);
    }

    function normalizeAnkiMathjaxTags(content) {
        return content.replace(/(<anki-mathjax\b[^>]*>)([\s\S]*?)(<\/anki-mathjax>)/gi, function(match, openTag, inner, closeTag) {
            return openTag + fixLatexSpan(inner) + closeTag;
        });
    }

    function wrapParentheticalMathPlain(content) {
        let result = '';
        let i = 0;
        while (i < content.length) {
            if (content[i] !== '(' || isEscaped(content, i)) {
                result += content[i];
                i++;
                continue;
            }

            const end = findMatchingParen(content, i);
            if (end === -1) {
                result += content[i];
                i++;
                continue;
            }

            if (i > 0 && /[A-Za-z]/.test(content[i - 1])) {
                result += content.slice(i, end + 1);
                i = end + 1;
                continue;
            }

            const inner = content.slice(i + 1, end);
            if (looksLikeMathSpan(inner) || /^\s*[A-Za-z]\s*$/.test(inner)) {
                result += '\\(' + fixLatexSpan(inner) + '\\)';
            } else {
                result += content.slice(i, end + 1);
            }
            i = end + 1;
        }
        return result;
    }

    function wrapParentheticalMath(content) {
        const mathBlock = /(\\\([\s\S]*?\\\)|\\\[[\s\S]*?\\\]|<anki-mathjax\b[^>]*>[\s\S]*?<\/anki-mathjax>)/gi;
        let result = '';
        let last = 0;
        let match;
        while ((match = mathBlock.exec(content)) !== null) {
            result += wrapParentheticalMathPlain(content.slice(last, match.index));
            result += match[0];
            last = match.index + match[0].length;
        }
        result += wrapParentheticalMathPlain(content.slice(last));
        return result;
    }

    function wrapBareMathTokensPlain(content) {
        const greek = 'lambda|alpha|beta|gamma|delta|epsilon|phi|theta|omega';
        let text = content.replace(/(^|[^\\A-Za-z0-9])([A-Za-z])\(([A-Za-z0-9_,+\-*/^ ]{1,40})\)/g, function(match, prefix, name, args) {
            return prefix + '\\(' + fixLatexSpan(name + '(' + args + ')') + '\\)';
        });
        text = text.replace(new RegExp('(^|[^A-Za-z0-9])(\\\\(?:' + greek + ')_[A-Za-z0-9]+)(?![A-Za-z0-9])', 'gi'), function(match, prefix, token) {
            return prefix + '\\( ' + fixLatexSpan(token) + ' \\)';
        });
        text = text.replace(new RegExp('(^|[^\\\\A-Za-z0-9])((?:' + greek + '|[A-Za-z])_[A-Za-z0-9]+)(?![A-Za-z0-9])', 'gi'), function(match, prefix, token) {
            return prefix + '\\( ' + fixLatexSpan(token) + ' \\)';
        });
        return text;
    }

    function wrapBareMathTokens(content) {
        const mathBlock = /(\\\([\s\S]*?\\\)|\\\[[\s\S]*?\\\]|<anki-mathjax\b[^>]*>[\s\S]*?<\/anki-mathjax>)/gi;
        let result = '';
        let last = 0;
        let match;
        while ((match = mathBlock.exec(content)) !== null) {
            result += wrapBareMathTokensPlain(content.slice(last, match.index));
            result += match[0];
            last = match.index + match[0].length;
        }
        result += wrapBareMathTokensPlain(content.slice(last));
        return result;
    }

    function shouldWrapStandaloneMath(content) {
        const stripped = String(content || '').trim();
        if (!stripped || stripped.length > 200 || /\\[\(\[]|<anki-mathjax/i.test(stripped) || !looksLikeMathSpan(stripped)) {
            return false;
        }
        if (stripped.includes(' ') && !/[=\\]/.test(stripped)) {
            return false;
        }
        let proseProbe = stripped.replace(/\\[A-Za-z]+(?:_[A-Za-z0-9]+)?/g, ' ');
        proseProbe = proseProbe.replace(/\b(?:exp|lambda|frac|left|right|sin|cos|tan|sqrt|log|ln|approx|cdot|partial|alpha|beta|gamma|delta|epsilon|phi|theta|omega)(?:_[A-Za-z0-9]+)?\b/gi, ' ');
        proseProbe = proseProbe.replace(/\b[A-Za-z]_[A-Za-z0-9]+\b/g, ' ');
        proseProbe = proseProbe.replace(/\b[A-Za-z]\b/g, ' ');
        const proseWords = proseProbe.match(/\b[A-Za-z]{2,}\b/g) || [];
        return proseWords.length <= 1;
    }

    function normalizeMathContent(value) {
        let content = String(value);
        content = content.replace(/\\\\([()\[\]])/g, '\\$1');
        content = normalizeAnkiMathjaxTags(content);
        content = normalizeDollarMathDelimiters(content);
        content = normalizeMixedMathDelimiters(content);
        content = content.replace(/\\\(([\s\S]*?)\\\)/g, function(match, inner) {
            return '\\(' + fixLatexSpan(inner) + '\\)';
        });
        content = content.replace(/\\\[([\s\S]*?)\\\]/g, function(match, inner) {
            return '\\[' + fixLatexSpan(inner) + '\\]';
        });
        if (!/<anki-mathjax/i.test(content)) {
            if (shouldWrapStandaloneMath(content)) {
                content = '\\(' + fixLatexSpan(content.trim()) + '\\)';
            } else {
                content = wrapParentheticalMath(content);
                content = wrapBareMathTokens(content);
            }
        }
        return content;
    }

    function appendRenderedContent(target, content) {
        const tagPattern = /<anki-mathjax\b[^>]*>([\s\S]*?)<\/anki-mathjax>/gi;
        let last = 0;
        let match;
        while ((match = tagPattern.exec(content)) !== null) {
            if (match.index > last) {
                target.appendChild(document.createTextNode(content.slice(last, match.index)));
            }
            const mathNode = document.createElement('anki-mathjax');
            mathNode.textContent = match[1];
            target.appendChild(mathNode);
            last = match.index + match[0].length;
        }
        if (last < content.length) {
            target.appendChild(document.createTextNode(content.slice(last)));
        }
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
            appendRenderedContent(li, normalizeMathContent(item));
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

    function renderMathjax(root, retryCount) {
        if (typeof MathJax !== 'undefined') {
            try {
                const target = root || document.body;
                // Check if MathJax is actually ready
                const isReady = typeof MathJax.typesetPromise === 'function' || 
                                (typeof MathJax.Hub !== 'undefined' && typeof MathJax.Hub.Queue === 'function');
                
                if (!isReady && (retryCount || 0) < 5) {
                    setTimeout(function() {
                        renderMathjax(root, (retryCount || 0) + 1);
                    }, 200);
                    return;
                }

                if (typeof MathJax.typesetPromise === 'function') {
                    // v3
                    MathJax.typesetPromise([target]).catch(function(err) {
                        console.warn('AI-Hints: MathJax typeset failed', err);
                    });
                } else if (typeof MathJax.typeset === 'function') {
                    // v3 alternative
                    MathJax.typeset([target]);
                } else if (typeof MathJax.Hub !== 'undefined' && typeof MathJax.Hub.Queue === 'function') {
                    // v2
                    MathJax.Hub.Queue(["Typeset", MathJax.Hub, target]);
                }
            } catch (err) {
                console.warn('AI-Hints: MathJax rendering error', err);
            }
        }
    }

    function revealAIHints(mode) {
        const container = selectCurrentBlock('.ai-hints-container[data-ai-hints-addon-id="2119980872"]');
        if (!container) return false;

        const current = currentCard();
        const uiCfg = window.aiHintsUiConfig || {};
        const reviewToken = uiCfg.review_token || '0';
        const cardKey = (current.id || '') + '_' + (current.ord || '0') + '_' + reviewToken;
        const state = Persistence.getState(cardKey) || { hints: false, options: false };

        const hintsList = container.querySelector('.ai-hints-hint-list');
        const optionsList = container.querySelector('.ai-hints-list');
        const hintBtn = document.querySelector('[data-ai-hints-action="toggle-hints"]');
        const showBtn = document.querySelector('[data-ai-hints-action="toggle-options"]');
        
        const showHintsCfg = uiCfg.auto_show_hints || container.getAttribute('data-show-hints') !== 'false';
        const showOptionsCfg = uiCfg.auto_show_options || container.getAttribute('data-show-options') !== 'false';

        let revealed = false;
        const revealHints = mode !== 'options';
        const revealOptions = mode !== 'hints';
        
        if (revealHints && hintsList && showHintsCfg) {
            hintsList.classList.remove('ai-hints-hidden');
            hintsList.style.display = 'block';
            if (hintBtn) {
                hintBtn.innerText = 'Hide Hints';
            }
            if (showBtn) {
                showBtn.style.display = 'inline-block';
            }
            state.hints = true;
            revealed = true;
        }
        if (revealOptions && optionsList && showOptionsCfg) {
            optionsList.classList.remove('ai-hints-hidden');
            optionsList.style.display = 'block';
            if (showBtn) {
                showBtn.style.display = 'inline-block';
                showBtn.innerText = 'Hide Options';
            }
            state.options = true;
            revealed = true;
        }
        
        if (revealed) {
            Persistence.saveState(cardKey, state);
            restartSpeedFocusTimer();
            renderMathjax(container);
        }
        return revealed;
    }

    function setupAIHints(manualData) {
        const current = currentCard();
        if (!current.id && current.ord == null) {
            return;
        }

        const uiCfg = window.aiHintsUiConfig || {};
        const reviewToken = uiCfg.review_token || '0';
        const cardKey = (current.id || '') + '_' + (current.ord || '0') + '_' + reviewToken;
        const cardBody = document.getElementById('qa');
        if (!cardBody) {
            setTimeout(function() { setupAIHints(manualData); }, 50);
            return;
        }
        
        // 1. Identify best available blocks before cleanup
        let container = selectCurrentBlock('.ai-hints-container[data-ai-hints-addon-id="2119980872"]');
        let jsonBlock = selectCurrentBlock('.ai-hints-json[data-ai-hints-addon-id="2119980872"]');
        let hasCurrentData = Boolean(container);

        // 2. Clean up old or non-matching blocks, but preserve our selected ones
        document.querySelectorAll('.ai-hints-container, .ai-hints-json, .ai-hints-actions').forEach(function(el) {
            if (el === container || el === jsonBlock) {
                return;
            }
            
            if (el.classList.contains('ai-hints-actions')) {
                el.remove();
                return;
            }

            // Remove if it definitely doesn't match the current card
            if (!matchesCurrentCard(el)) {
                el.remove();
            } else if (document.getElementById('qa')?.contains(el)) {
                // If it matches but we already found a better one (e.g. this is a duplicate in QA)
                el.remove();
            } else {
                // It's outside QA and matches, but we already have a better one selected?
                // If we already have a selected block, we can remove this extra one.
                if (container || jsonBlock) {
                     el.remove();
                }
            }
        });

        if (!manualData && !jsonBlock) {
            // Check if we have data in session storage for this card
            const cachedData = Persistence.getData(cardKey);
            if (cachedData) {
                manualData = cachedData;
            }
        }

        // Only remove existing container to force complete recreation if we have JSON or manual data to rebuild it from
        if (container && (jsonBlock || manualData)) {
            container.remove();
            container = null;
            hasCurrentData = false;
        }

        if ((jsonBlock || manualData) && !container) {
            try {
                let data;
                if (manualData) {
                    data = manualData;
                } else {
                    const rawData = (jsonBlock.textContent || jsonBlock.innerText || '').trim();
                    data = JSON.parse(rawData);
                }

                // Handle keyed JSON (e.g., { "c1": { "hints": [...], "options": [...] } })
                if (data && !data.hints && !data.options) {
                    const current = currentCard();
                    const cardKey = 'c' + ((current.ord || 0) + 1);
                    if (data[cardKey]) {
                        data = data[cardKey];
                    } else {
                        data = null;
                    }
                }

                if (data && (Array.isArray(data.hints) || Array.isArray(data.options))) {
                    container = document.createElement('div');
                    container.className = 'ai-hints-container';
                    applyAddonAttrs(container);
                    hasCurrentData = true;

                    container.appendChild(document.createElement('hr'));
                    const hintsSection = createListSection('AI Hints:', 'ai-hints-hint-list', data.hints);
                    const optionsSection = createListSection('AI Options:', 'ai-hints-list', data.options);
                    if (hintsSection) {
                        container.appendChild(hintsSection);
                    }
                    if (optionsSection) {
                        container.appendChild(optionsSection);
                    }

                    if (jsonBlock) {
                        jsonBlock.parentNode.insertBefore(container, jsonBlock.nextSibling);
                        copyCardAttrs(jsonBlock, container);
                    } else {
                        applyCurrentCardAttrs(container);
                        cardBody.appendChild(container);
                    }
                }
            } catch (e) {
                console.error("AI-Hints: Failed to parse JSON options", e);
            }
        }

        const showOnCard = uiCfg.show_on_card !== false;
        
        if (!showOnCard && !container) {
            return;
        }

        const btnContainer = document.createElement('div');
        btnContainer.className = 'ai-hints-actions';
        applyCurrentCardAttrs(btnContainer);
        btnContainer.style.marginTop = '10px';
        btnContainer.style.textAlign = 'center';

        let hintsList = null;
        let optionsList = null;
        let showHintsCfg = true;
        let showOptionsCfg = true;

        if (container) {
            // Only show if it matches the current card
            if (manualData || matchesCurrentCard(container)) {
                hasCurrentData = true;
                container.style.display = 'block';
                hideOtherContainers(container);
                optionsList = container.querySelector('.ai-hints-list');
                hintsList = container.querySelector('.ai-hints-hint-list');
                
                showHintsCfg = uiCfg.auto_show_hints || container.getAttribute('data-show-hints') !== 'false';
                showOptionsCfg = uiCfg.auto_show_options || container.getAttribute('data-show-options') !== 'false';
                
                const state = Persistence.getState(cardKey) || { hints: false, options: false };

                // Reset and shuffle options
                if (optionsList) {
                    const items = Array.from(optionsList.children);
                    for (let i = items.length - 1; i > 0; i--) {
                        const j = Math.floor(Math.random() * (i + 1));
                        [items[i], items[j]] = [items[j], items[i]];
                    }
                    items.forEach(item => optionsList.appendChild(item));
                    
                    if (state.options && showOptionsCfg) {
                        optionsList.classList.remove('ai-hints-hidden');
                        optionsList.style.display = 'block';
                    } else {
                        optionsList.classList.add('ai-hints-hidden');
                        optionsList.style.display = 'none';
                    }
                }

                if (hintsList) {
                    if (state.hints && showHintsCfg) {
                        hintsList.classList.remove('ai-hints-hidden');
                        hintsList.style.display = 'block';
                    } else {
                        hintsList.classList.add('ai-hints-hidden');
                        hintsList.style.display = 'none';
                    }
                }
            } else {
                container.style.display = 'none';
            }
        }

        const triggerGenerate = function(btn) {
            restartSpeedFocusTimer();
            btn.disabled = true;
            btn.innerHTML = '✨ Generating...';
            btn.classList.add('ai-hints-btn-generating');
            sendCommand('ai_hints_generate');
        };

        const hasAnyData = Boolean(hasCurrentData || manualData);
        const mainGenBtn = document.createElement('button');
        mainGenBtn.className = 'ai-hints-btn';
        mainGenBtn.dataset.aiHintsAction = 'generate';
        
        const isGenerating = uiCfg.is_generating || false;
        if (isGenerating) {
            mainGenBtn.innerHTML = '✨ Generating...';
            mainGenBtn.disabled = true;
            mainGenBtn.classList.add('ai-hints-btn-generating');
        } else {
            mainGenBtn.innerText = hasAnyData ? 'Regenerate' : 'Generate AI Hints';
            mainGenBtn.onclick = function() {
                triggerGenerate(mainGenBtn);
            };
        }
        btnContainer.appendChild(mainGenBtn);

        const optBtn = document.createElement('button');
        optBtn.innerText = 'Show Options';
        optBtn.className = 'ai-hints-btn';
        optBtn.dataset.aiHintsAction = 'toggle-options';
        setButtonEnabled(optBtn, Boolean(optionsList && optionsList.children.length > 0));
        optBtn.onclick = function() {
            if (!optionsList) {
                return;
            }
            restartSpeedFocusTimer();
            const isHidden = optionsList.classList.contains('ai-hints-hidden');
            optionsList.classList.toggle('ai-hints-hidden');
            optionsList.style.display = isHidden ? 'block' : 'none';
            optBtn.innerText = isHidden ? 'Hide Options' : 'Show Options';
            
            const state = Persistence.getState(cardKey) || { hints: false, options: false };
            state.options = isHidden;
            Persistence.saveState(cardKey, state);

            if (isHidden) {
                renderMathjax(container);
            }
        };
        btnContainer.appendChild(optBtn);

        const hintBtn = document.createElement('button');
        hintBtn.innerText = 'Show Hints';
        hintBtn.className = 'ai-hints-btn';
        hintBtn.dataset.aiHintsAction = 'toggle-hints';
        setButtonEnabled(hintBtn, Boolean(hintsList && hintsList.children.length > 0));
        hintBtn.onclick = function() {
            if (!hintsList) {
                return;
            }
            restartSpeedFocusTimer();
            const isHidden = hintsList.classList.contains('ai-hints-hidden');
            hintsList.classList.toggle('ai-hints-hidden');
            hintsList.style.display = isHidden ? 'block' : 'none';
            hintBtn.innerText = isHidden ? 'Hide Hints' : 'Show Hints';

            const state = Persistence.getState(cardKey) || { hints: false, options: false };
            state.hints = isHidden;
            Persistence.saveState(cardKey, state);

            if (isHidden) {
                renderMathjax(container);
            }
        };
        btnContainer.appendChild(hintBtn);

        const clearBtn = document.createElement('button');
        clearBtn.innerText = 'Clear';
        clearBtn.className = 'ai-hints-btn ai-hints-btn-secondary';
        clearBtn.dataset.aiHintsAction = 'clear';
        setButtonEnabled(clearBtn, hasAnyData);
        clearBtn.onclick = function() {
            if (!hasAnyData) {
                return;
            }
            if (confirm('Clear AI hints for this card?')) {
                clearBtn.disabled = true;
                clearBtn.innerText = 'Clearing...';
                sendCommand('ai_hints_clear');
            }
        };
        btnContainer.appendChild(clearBtn);

        // Refresh Button (Always useful)
        const refreshBtn = document.createElement('button');
        refreshBtn.innerText = 'Refresh';
        refreshBtn.className = 'ai-hints-btn ai-hints-btn-secondary';
        refreshBtn.dataset.aiHintsAction = 'refresh';
        refreshBtn.title = 'Refresh hints from card cache';
        refreshBtn.onclick = function() {
            restartSpeedFocusTimer();
            refreshBtn.disabled = true;
            refreshBtn.innerText = 'Refreshing...';
            sendCommand('ai_hints_refresh');
            setTimeout(function() {
                if (refreshBtn) {
                    refreshBtn.disabled = false;
                    refreshBtn.innerText = 'Refresh';
                }
            }, 2000);
        };
        btnContainer.appendChild(refreshBtn);

        // JSON View Button
        const jsonViewBtn = document.createElement('button');
        jsonViewBtn.innerText = 'Show JSON';
        jsonViewBtn.className = 'ai-hints-btn ai-hints-btn-secondary';
        jsonViewBtn.dataset.aiHintsAction = 'show-json';
        jsonViewBtn.title = 'Show raw JSON data';
        setButtonEnabled(jsonViewBtn, hasAnyData);
        jsonViewBtn.onclick = function() {
            if (!container) return;
            let view = container.querySelector('.ai-hints-json-view');
            if (view) {
                view.remove();
                jsonViewBtn.innerText = 'Show JSON';
            } else {
                view = document.createElement('div');
                view.className = 'ai-hints-json-view';
                
                // Try to get data from jsonBlock or container
                const targetJsonBlock = selectCurrentBlock('.ai-hints-json[data-ai-hints-addon-id="2119980872"]');
                let raw = '';
                if (manualData) {
                    raw = JSON.stringify(manualData, null, 2);
                } else if (targetJsonBlock) {
                    try {
                        raw = JSON.stringify(JSON.parse(targetJsonBlock.textContent), null, 2);
                    } catch(e) {
                        raw = targetJsonBlock.textContent;
                    }
                }
                
                view.textContent = raw || 'No JSON data found.';
                container.appendChild(view);
                jsonViewBtn.innerText = 'Hide JSON';
            }
        };
        btnContainer.appendChild(jsonViewBtn);

        if (container && container.style.display !== 'none') {
            // Ensure container is in the visible area (#qa) if it was injected outside (e.g. on front side)
            if (cardBody && cardBody !== document.body && !cardBody.contains(container)) {
                cardBody.appendChild(container);
            }
            const separator = container.querySelector('hr');
            container.insertBefore(btnContainer, separator ? separator.nextSibling : container.firstChild);
        } else {
            btnContainer.style.margin = '20px auto';
            cardBody.appendChild(btnContainer);
        }

        if (uiCfg.auto_reveal || manualData) {
            if (uiCfg.auto_show_hints && uiCfg.auto_show_options) {
                revealAIHints();
            } else if (uiCfg.auto_show_options) {
                revealAIHints('options');
            } else {
                // Default to showing hints if manual generation finished
                revealAIHints('hints');
            }
        } else {
            if (uiCfg.auto_show_hints && uiCfg.auto_show_options) {
                revealAIHints();
            } else if (uiCfg.auto_show_hints) {
                revealAIHints('hints');
            } else if (uiCfg.auto_show_options) {
                revealAIHints('options');
            }
        }

        if (container && container.style.display !== 'none') {
            renderMathjax(container);
        }
    }

    window.aiHintsUpdateData = function(data) {
        if (window.aiHintsUiConfig) {
            window.aiHintsUiConfig.is_generating = false;
        }
        const current = currentCard();
        const uiCfg = window.aiHintsUiConfig || {};
        const reviewToken = uiCfg.review_token || '0';
        const cardKey = (current.id || '') + '_' + (current.ord || '0') + '_' + reviewToken;
        if (current.id) {
            Persistence.saveData(cardKey, data);
            // Reset state for new generation
            Persistence.saveState(cardKey, { hints: true, options: false });
        }
        setupAIHints(data);
    };

    window.aiHintsClearData = function() {
        if (window.aiHintsUiConfig) {
            window.aiHintsUiConfig.is_generating = false;
        }
        const current = currentCard();
        const uiCfg = window.aiHintsUiConfig || {};
        const reviewToken = uiCfg.review_token || '0';
        const cardKey = (current.id || '') + '_' + (current.ord || '0') + '_' + reviewToken;
        if (current.id) {
            Persistence.saveData(cardKey, null);
            Persistence.saveState(cardKey, null);
        }
        document.querySelectorAll('.ai-hints-container[data-ai-hints-addon-id="2119980872"], .ai-hints-json[data-ai-hints-addon-id="2119980872"]').forEach(function(block) {
            if (matchesCurrentCard(block)) {
                block.remove();
            }
        });
        setupAIHints();
    };

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

            const container = selectCurrentBlock('.ai-hints-container');
            if (!container) {
                event.preventDefault();
                event.stopPropagation();
                restartSpeedFocusTimer();
                sendCommand('ai_hints_generate');
                return;
            }

            const hintsList = container.querySelector('.ai-hints-hint-list');
            const optionsList = container.querySelector('.ai-hints-list');
            const showHintsCfg = container.getAttribute('data-show-hints') !== 'false';
            const showOptionsCfg = container.getAttribute('data-show-options') !== 'false';

            const hintsHidden = hintsList && hintsList.classList.contains('ai-hints-hidden') && showHintsCfg;
            const optionsHidden = optionsList && optionsList.classList.contains('ai-hints-hidden') && showOptionsCfg;

            if (hintsHidden) {
                if (revealAIHints('hints')) {
                    event.preventDefault();
                    event.stopPropagation();
                }
            } else if (optionsHidden) {
                if (revealAIHints('options')) {
                    event.preventDefault();
                    event.stopPropagation();
                }
            } else {
                event.preventDefault();
                event.stopPropagation();
            }
        }, true);
    }
    
    if (!window.aiHintsKeyBound) {
        window.aiHintsKeyBound = true;
        document.addEventListener('keydown', function(e) {
            if (!e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) {
                return;
            }
            
            if (isEditableTarget(document.activeElement)) {
                return;
            }

            let action = null;
            switch (e.key) {
                case '1': action = 'generate'; break;
                case '2': action = 'toggle-options'; break;
                case '3': action = 'toggle-hints'; break;
                case '4': action = 'clear'; break;
                case '5': action = 'refresh'; break;
                case '6': action = 'show-json'; break;
            }

            if (!action) return;

            const btn = document.querySelector('[data-ai-hints-action="' + action + '"]');
            if (btn && !btn.disabled && btn.style.display !== 'none' && getComputedStyle(btn).display !== 'none') {
                e.preventDefault();
                e.stopPropagation();
                btn.click();
            }
        }, true);
    }


})();
