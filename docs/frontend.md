# AI-Hints Frontend (JavaScript) Reference

This page documents the JavaScript that renders AI-Hints in the Anki reviewer and on mobile devices. It describes the single unified script, the two files it exists as, the runtime globals it reads, the data it consumes, and how it talks back to the Python add-on.

## The Unified Renderer

There is **one** script that powers every platform:

| File | Where | Role |
|------|-------|------|
| `addon/web/template.js` | Source of truth (in the add-on package) | The actual JavaScript. |
| `_ai_hints_template.js` | Your Anki **media folder** | An exact synced copy of `template.js`. |

They are byte-for-byte identical (`diff` should be clean). `mobile_sync.sync_mobile_script()` (addon/mobile_sync.py:13) copies `web/template.js` to `collection.media/_ai_hints_template.js`, writing only when the content changed. The add-on calls this automatically (deferred) on profile load, and you can re-run it from **Mobile Support** by clicking **One-Click Install: Setup All Note Types**.

## How It Gets Into a Card

The script is injected into card templates with a block wrapped in `<!-- AI-HINTS-BEGIN -->` … `<!-- AI-HINTS-END -->`:

```html
<div style="display:none;">{{AI Hints}}</div>
<ai-hints></ai-hints>
<script>
window.aiHintsMobileConfig = { /* ... */ };
</script>
<script src='_ai_hints_template.js'></script>
```

Builders: `mobile_sync._get_full_template_block()` and `config_ui/tab_mobile.py:149`.

On **Desktop**, the Python add-on additionally injects a `state_js` script at the end of the webview body (reviewer_hooks.py:766) that wipes stale elements and sets:

```javascript
window.aiHintsCurrentCard = {"id": ..., "ord": ...};
window.aiHintsUiConfig = { /* desktop UI/settings config */ };
```

On **Mobile** (no Python), only the template's `window.aiHintsMobileConfig` is present.

## Runtime Globals

These are the window globals `template.js` reads (with `const isAddonActive = !!window.aiHintsUiConfig;` at the top distinguishing desktop vs mobile).

| Global | Set by | Meaning |
|--------|--------|---------|
| `window.aiHintsUiConfig` | Desktop Python (`state_js`) | If present, the add-on is active → full control (Generate, Clear, edit, etc.). Carries `is_answer_side`, auto-show flags (`auto_show_hints`, etc.), `review_token`, `hints_font_size`, `is_generating`, and more. Its *presence* (truthiness) toggles active mode. |
| `window.aiHintsMobileConfig` | Note-template script | Mobile-only config: `useEmojis`, `showExtraButtons`, `autoShowHints`, `autoShowOptions`, `autoShowHintsAnswer`, `autoShowOptionsAnswer`, `optionsBeforeHints`, `shortcuts`. |
| `window.aiHintsCurrentCard` | Desktop `state_js` | `{ id, ord }` of the current card; used to key state and scope rendering. Falls back to a hash (`id = 'temp'` / `'h'+hash`) when absent. |
| `window.aiHintsUnifiedLoaded` | template.js | Diagnostic flag set to `true` on load. |
| `window.aiHintsRetryState` | template.js | Tracks init retry attempts per card (`retryInitForCard`). |

## Data Contract

The renderer consumes **hidden JSON `<div class="ai-hints-json">` blocks** embedded in the note. Multiple ordinals for a cloze card are keyed as `c1`, `c2`, … Each card's payload is:

```json
{
  "hints": ["..."],
  "options": ["..."],
  "correct_answer": "...",
  "_provider": "...",
  "_model": "...",
  "_generated_at": "2026-08-12 17:46:16",
  "_generation_type": "batch",
  "_src": "...",
  "_skipped": true
}
```

- `hints` → the collapsible Hints panel.
- `options` → the interactive MCQ panel (distractor order is seeded/shuffled per card, see `shuffle(array, seed)`).
- `correct_answer` → drives which option highlights green.
- `_skipped: true` → renders the "AI generation skipped" message instead of data.

See [Data & Storage Format](data-format.md) for the full field reference.

## Rendering & State Model

- `init(manualData, isManualAction)` (template.js:947) is the entry point: prune stale/foreign blocks, compute `cardId`/`cardKey`/`cardOrd`, decide fresh-show vs re-show, apply auto-show defaults, and render.
- Rendering **replaces** any static `.ai-hints-container`s on the page with live UI built by `renderSection(parent, title, items, ...)` (hints vs options) and `renderMath` / `convertMathDelimitersToTags` for LaTeX.
- Collapsed/expanded state persists via `getPersistence()` (template.js:156) keyed by `state_<cardId>_<ord>`. A changed `review_token` (fresh card show / relearn) resets to the configured auto-show defaults and collapses the JSON panel.
- The JSON panel (📝 button) shows the raw payload inline.
- Options are clickable: tapping one records the selection, colors it green/red on the answer side, and reveals the answer (platform-specific — see [Mobile Setup](mobile-setup.md)).

## The `pycmd` Protocol (Desktop only)

When the add-on is active, the script calls Anki's `pycmd(...)` bridge to ask Python for actions:

| Command | Action |
|---------|--------|
| `pycmd('ai_hints_generate')` | Generate hints/options for the current card. |
| `pycmd('{"action":"ai_hints_generate_override", "provider":..., "model":...}')` | Regenerate using a specific provider+model (Alt+click). |
| `pycmd('ai_hints_cancel')` | Cancel an in-progress generation. |
| `pycmd('ai_hints_clear')` | Permanently clear the card's hints. |
| `pycmd('ai_hints_skip')` | Skip AI generation for the card. |
| `pycmd('ai_hints_refresh')` | Refresh the rendered data from the note. |
| `pycmd('ai_hints_remove_warning')` | Dismiss a factual-error ⚠️ warning hint. |
| `pycmd('ai_hints_edit_item')` | Persist an inline-edit to a hint/option. |
| `pycmd('ai_hints_rate_good')` / `'ai_hints_rate_again'` | Auto-rate the card (optional auto-rate feature). |

After generation, Python pushes fresh data back through `init(manualData, isManualAction)` (the `manualData` argument tells the renderer it is an update, so it labels buttons `Regenerate`).

## Development

1. Edit `addon/web/template.js` (the source).
2. Re-sync to the media folder for the change to appear:
   ```shell
   cp addon/web/template.js ~/.local/share/Anki2/default/collection.media/_ai_hints_template.js
   ```
   (Or use **Mobile Support → One-Click Install** / restart Anki, which auto-syncs.)
3. On **AnkiDroid**, the OS WebView aggressively caches the file — see [Mobile Setup → AnkiDroid Cache](mobile-setup.md#-troubleshooting-ankidroid-cache-webview) for the force-refresh procedure.

> **Note:** Keep `web/template.js` and `_ai_hints_template.js` identical. run the add-on's auto-sync or the manual copy above; never hand-edit the media copy.