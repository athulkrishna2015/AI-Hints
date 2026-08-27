# Configuration

Open the configuration window via **Tools → Add-ons → AI-Hints → Config**. It contains eight tabs:

1. [General](#general-tab)
2. [AI Providers](#ai-providers-tab)
3. [Advanced](#advanced-tab)
4. [Shortcuts](#shortcuts-tab)
5. [Batch Generation](#batch-generation-tab)
6. [Mobile Support](#mobile-support-tab)
7. [Support Authors](#support-authors-tab)
8. [Logs](#logs-tab)

The dialog opens non-modally and remembers your last tab. Closing it does not show an unsaved-changes confirmation.

> For a raw reference of every config key, default, and purpose, see [Configuration Reference (all keys)](config-reference.md).

## Bottom Action Bar (shared across all tabs)

| Button | What it does |
|--------|--------------|
| **Restore Defaults** | Restores default values for the currently selected tab (General / AI Providers / Advanced). |
| **🛑 Stop All** | Emergency stop for all background tasks and batch generations. |
| **Save** | Saves config and syncs mobile **without closing** the window. |
| **Save & Close** | Saves config, syncs mobile, then closes the window. |
| **Cancel** | Closes without saving (triggers an unsaved-changes prompt). |

---

## General Tab

### MCQ & Math

- **Number of Options:** — how many MCQ options the AI generates per card (range 1–10, default 4).
- **Answer Display Position:** — `between` (Front, AI Data, Back) or `bottom` (Front, Back, AI Data).
- **Repair AI LaTeX Errors** — auto-fixes common AI math errors (missing backslashes/delimiters). Default off.

### Generation (Master Switch)

- **Generate Hints** — master switch for hint generation everywhere (manual, auto, pre-gen, batch).
- **Generate Options (MCQ)** — master switch for MCQ generation.
- Turning **both** off disables the add-on entirely — no API calls are made anywhere. Provider **Test** buttons still work.

### Button Visibility

- **Show Hints Button** — render the collapsible "Hints" container.
- **Show Options Button (Sequential)** — render the clickable "Options" container.
- **Show Generate Button on Review Card** — embed generation controls (Generate/Regenerate/Clear) inline inside the card.

### Auto-Show & Generation

- **Auto Generate for New Cards** — master switch for automatic generation. When off, the sub-options below are disabled.
  - **Force Regenerate Even if Data Exists** — always overwrite hints.
  - **Regenerate if Generated Version <** — regenerate cards whose version is older than the entered value (e.g. `1.4.2`).
  - **Regenerate if Generated Time <** — regenerate cards generated before a date (`YYYY-MM-DD` or `YYYY-MM-DD HH:MM:SS`).
  - **Regenerate if Card Modified > Generated Date** — regenerate if the note was edited after generation.
- **Pre-generate ahead** + **Buffer size** — pre-generate upcoming cards in the background (buffer 1–10).

**On Card Load:**
- **Auto Show Hints** / **Auto Show Options** — expand hints/options when a card loads.

**On Back Side (Answer):**
- **Auto Show Hints** / **Auto Show Options** — expand hints/options on the answer side.

- **Show Options Above Hints** — display the options section before the hints section on the card. Enabled by default; unchecking it renders hints first, then options (and reorders the toggle buttons to match). Applies to both desktop review and mobile templates.

Each card resets to these defaults on a fresh show (including relearn/retries), so collapsed state never bleeds between cards.

### Auto-Rating

- **Auto Rate Good on Correct Option** + **Delay** — clicking the correct option auto-rates "Good" after the delay (default 0s).
- **Auto Rate Again on Wrong Option** + **Delay** — clicking a wrong option reveals the answer and rates "Again" (default 1s).

### Note Tagging

- **Tag Notes with AI Hints** + tag field — tag notes when hints are generated (removed on clear/skip). Enables fast batch scanning.
- **Tag Skipped Notes** + tag field — tag notes when AI is skipped.

### After Manual Generation

- **Auto Show Hints** / **Auto Show Options** — expand hints/options after clicking Generate/Regenerate.

---

## AI Providers Tab

### Model Names & Fallback Priority

Top row buttons:

- **Fetch All** — fetch the latest models for all providers that have API keys. When used in the Advanced Global Fallback dialog, it only updates the global list state and does not rewrite per-provider fallback checkboxes or ordering.
- **Test All** — test all configured/enabled providers sequentially.
- **Restore Defaults** — restore model names to factory defaults.

Global fallback controls:

- **Enable Advanced Fallback Priority (Global List)** — use a global priority list instead of per-provider nested fallbacks.
- **Advanced Fallback Priority...** — open the global priority dialog (drag & drop cross-provider ordering). Its enabled/disabled state is stored separately from the per-provider fallback lists.

### Per-Provider Rows

Each provider in your priority order has a row with:

| Control | What it does |
|---------|--------------|
| **Enable checkbox** | Enable/disable fallback to this provider. |
| **API Key field** | Paste your key(s); supports multiple named keys. |
| **🔑** | Open the Manage Multiple API Keys dialog. |
| **👁️** | Toggle API key visibility. |
| **▲ / ▼** | Reorder the provider in the priority list. |
| **Active Model combo** | Select the active model (editable). |
| **Fetch** | Fetch the latest models from the provider's API. |
| **Test** | Run a real test generation. |
| **Fallbacks** | Open the per-provider fallback priority dialog. |
| **Timeout spin** | Per-provider timeout (0–300s; 0 = use global). |
| **Status label** | Shows ✅ / ❌ / ⏳ / 🚫 Blacklisted. |

#### Fallback Priority Dialog (per provider)

- Search field to filter models.
- Table with **Model Name**, **Thinking Level** (`off`/`low`/`medium`/`high`), and **Timeout (s)** per model.
- Status markers: ⭐ active, 🆕 newly fetched (green), ⚠️ deprecated (red), ⚠️ no longer returned (amber). These markers are independent from the Advanced Global Fallback dialog.
- Buttons: **Move Up / Move Down / Set Active**, **Remove** (Selected / Deprecated / No Longer Returned / both), **Test** (Checked / Row / All), **Rank Checked First**, **Fetch All**, **Restore Defaults**.
- Fetching models in this dialog preserves the current checked state for rows that already exist; newly fetched rows stay unchecked until you enable them.

### Model Testing Prompt Settings

- **Test Question (Front)** / **Test Answer (Back)** — the question/answer used when testing models.
- **Reset to Default** — restore the default test prompt.

### Custom Providers

- **Add / Edit / Remove** — manage custom OpenAI-compatible endpoints.
- **Provider Name (ID)** — unique name.
- **Endpoint URL** — auto-normalized (e.g. `http://localhost:11434/v1`).
- **API Key** — optional for local endpoints; supports multiple keys.
- **Model Name** + **Fetch** — the model to use.
- **Models URL (optional)** — separate URL for model discovery.
- **Headers (JSON)** — extra request headers to include on every call to this provider. These are merged over the default `Content-Type: application/json` / `Accept: application/json` / `Authorization: Bearer <key>` headers. Common uses:
  - `{"HTTP-Referer": "https://example.com"}` and `{"X-Title": "My App"}` — required by OpenRouter-style proxies.
  - `{"X-API-Key": "..."}` — for APIs that expect a custom auth header instead of `Authorization`.
  - Provider-specific headers (e.g. vendor/account IDs, custom auth tokens).
  - Example: `{"X-Custom-Host": "prod", "X-Api-Version": "2026-01-01"}`
- **Body Params (JSON)** — extra JSON fields merged into the request body, alongside `model` and `messages`. Useful for provider-specific options not exposed in the UI:
  - Disable streaming: `{"stream": false}`.
  - Web search / grounding: `{"web_search_options": {}}`.
  - Reasoning/thinking level: `{"think": "low"}` (or `"medium"` / `"high"`; `"off"` disables). Note: per-model thinking levels configured in the Fallback dialog override this field.
  - Other vendor options, e.g. `{"temperature": 0.7, "max_tokens": 1024}`.
  - Example: `{"stream": false, "web_search_options": {}, "temperature": 0.7}`

---

## Advanced Tab

### System Prompt

- **Additional System Instructions (Appended to Default Prompt)** — free-text appended to the default system prompt (the core prompt itself is not editable from the dialog).

### Model Cooldowns & Blacklist

- **Sort By** — Name / Time Remaining (Desc/Asc) / Failure Streak.
- **Blacklist list** — shows each blacklisted provider-model-key combo and its failure streak.
- **Remove Selected** / **Clear All Cooldowns** — manage the blacklist.
- **Default Failure Lockout (mins)** — cooldown duration after repeated failures (default 10, range 1–1440).
- **API Request Timeout (seconds)** — active-review timeout (default 60).
- **Pregen Timeout (seconds)** — pre-generation timeout (default 120).

### Visual Styling

- **Hints Font Size** — font size for hints/options (inherit, `0.75em`–`1.2em`, `12px`–`18px`).

### Maintenance Tools

- **Scope Task To** — searchable deck selector; run tools on a specific deck or the entire collection.
- **🔣 Convert Unicode Escapes** — convert `\uXXXX` escapes to readable text.
- **Only scan notes modified since last clean scan** — speed up scans by only checking edited notes.
- **🧹 Clean Orphaned Hints** — remove hint data for clozes that no longer exist.
- **🗑️ Purge Naked JSON Blocks** — remove raw JSON pasted without the div wrapper.
- **🧹 Clear Pregen Cache** — clear the pre-generated disk cache.
- **🏷️ Tag All Cards with Hints** — tag every note with saved hint data so fast batch-scan can skip them.

### Raw Editor

- **Show Raw JSON Editor** — toggle a text editor with the full serialized config. When checked and saved, the raw JSON is written directly.

---

## Shortcuts Tab

### Primary Shortcuts

- **Shortcut Modifier(s)** — Ctrl / Alt / Shift / Meta (multiple can be combined).
- **Generate / Regenerate** — default `1`.
- **Toggle Options** — default `3`.
- **Toggle Hints** — default `2`.
- **Clear** — default `4` (irrevocably wipes the hints payload).
- **Refresh** — default `5`.
- **Show JSON** — default `6` (debug panel).

On the front side, these also work without the modifier.

### MCQ Option Selection Keys

- **Select Options Modifier(s)** — default `none`.
- **Select Options Keys** — default `1-9` (1 = 1st option, 2 = 2nd, etc.).

A note on shortcut collisions: `ctrl` is used by Anki for flags, `alt` by some OSes, `meta` by the OS dock. The add-on recommends `ctrl+shift` if you change modifiers.

### Fixed Reviewer Shortcuts

Two bindings are independent of the modifier scheme above:

- `Ctrl+Alt+Z` — Undo last AI update (steps back: replaced result → … → original value).
- `Ctrl+Alt+Shift+Z` — Redo last undone AI update.

---

## Batch Generation Tab

### Start New Batch Generation

- **Method Type** — `Sequential Local Queue (Recommended)` or `Native Async API (Cloud)` (Gemini only, paid billing, no fallbacks).
- **Force Provider** — override which provider the batch uses (default follows the fallback matrix).
- **Force Model** — override which model to use (default system default).
- **Source Deck** — which deck to batch (autocomplete supported).
- **Skip cards that already have AI Hints generated** — skip cards already having hints.
- **🧹 Force FULL scan (ignore last-scan cursor)** — re-check every card.
- **Except if Generated Version <** — still queue older-version cards.
- **Batch Limit** — max cards to process (default 1000).
- **Concurrent Multi-Provider Generation (Multithreaded)** — generate in parallel using all ready/enabled providers.

### Running & Pending Batches

- **🚀 Initiate Queue** — start/pause/resume the batch.
- **🛑 Stop & Discard Queue** — stop and clear.
- **🔄 Refresh Status** — refresh the view (auto-refreshes every 5s).
- Live status log with clickable card links, discard buttons, and job reordering.

---

## Mobile Support Tab

### Mobile Display Options

- **Use Emojis instead of text labels (saves space)** — use 💡/🎯 instead of "Show Hints"/"Show Options".
- **Show extra button (Refresh)** — add the 🔄 Refresh button (📝 Show JSON is always available).

### Template Setup

- **One-Click Install: Setup All Note Types** — installs the script and updates all templates, then triggers AnkiWeb sync.
- **Remove from All Note Types** — removes AI-Hints tags/blocks and deletes `_ai_hints_template.js`, then syncs.
- **Manual Installation** — script preview + **Copy Manual Script to Clipboard** for manual template setup.

See [Mobile Support](mobile-setup.md) for full instructions.

---

## Support Authors Tab

- **I have supported this addon (Hide automatic update welcome)** — stored in addon meta; prevents the Support tab from auto-opening after updates.
- **Ko-fi** widget / button.
- **UPI**, **BTC**, and **ETH** QR codes with copyable addresses.

---

## Logs Tab

### Filter bar

- **Level** — ALL / DEBUG / INFO / WARNING / ERROR.
- **Source** — ALL / Antigravity Proxy / Batch Processing / Pre-generation / Model Testing / Lingering / Standard Addon. **Lingering** isolates the `AI-Hints Linger: ...` background-timeout lines (late-arriving results, higher-priority race wins, total-failure rescue).
- **Search** — text filter (debounced).
- Match count label.

### Controls

- **Clear on startup** — clear the log file every Anki start.
- **Debug logging** — enable verbose DEBUG output immediately (no restart needed).
- **Refresh** — manually refresh the view (auto-refreshes every 1s while active).
- **Copy** — copy the log to clipboard.
- **Clear Log** — empty the log file.

### Log view

Read-only monospace view with color-coded severity, clickable URLs and 13-digit Anki card IDs (opens in Browser), and highlighted search terms.
