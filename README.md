# AI-Hints Anki Add-on

AI-Hints is a powerful Anki add-on that uses Artificial Intelligence to generate helpful hints or multiple-choice options for your flashcards during review. It helps simulate real exam conditions by including the correct answer alongside plausible distractors even for open-ended cards.

Install from [anki web ](https://ankiweb.net/shared/info/2119980872)

github:[https://github.com/athulkrishna2015/AI-Hints](https://github.com/athulkrishna2015/AI-Hints)

## Features

- **Multi-Provider Support**: Supports OpenAI, Anthropic, Gemini, Groq, DeepSeek, NVIDIA, Mistral, Grok, OpenRouter, **Together AI**, **Hugging Face**, **SambaNova**, **Cerebras**, **Antigravity Proxy**, and any OpenAI-compatible local API (like Ollama or LM Studio).
- **Native Antigravity Daemon**: Features seamless embedded integration of the [Antigravity Cloud Proxy](https://github.com/frieser/antigravity-proxy). Automatically manages background executable lifecycle, offers one-click account setup dashboard, and provides direct gateway to premier LLMs completely locally.
- **Unified UI System**: Desktop and Mobile now share the exact same rendering engine (`template.js`), ensuring consistent features (like shuffling and MathJax) across all devices.
- **Cross-Platform Support**: Includes a **Unified UI** script that works on AnkiDroid, AnkiMobile, and AnkiWeb even without the add-on installed. Includes a **Smart One-Click Installer** that automatically manages your templates and keep them in sync.
- **Smart Auto-Updates**: Once you've opted-in via the Installer, the addon automatically keeps your mobile setup up to date whenever you update the addon or change settings.
- **Compact Emoji Mode**: Optional ultra-compact UI for mobile that uses pure emojis (💡, 🎯, 🗑️) instead of text labels.
- **HTML-Aware Clearing**: Re-engineered the "Clear" logic to aggressively remove redundant `<br>` tags and empty lines to keep your cards perfectly clean.
- **Edit Field Compatibility**: Improved compatibility with "Edit Field During Review Native" — UI updates now pause while you are typing to prevent focus loss.
- **Automatic Fallback**: If your primary AI provider fails (e.g., rate limits or API downtime), the add-on automatically attempts to generate hints using your next provider.
- **Model Fallbacks**: Each provider has its own **intelligence-ranked fallback hierarchy** to automatically retry next-best models before switching to a different provider.
- **Multi-Cloze Support**: Optimized for cards with multiple cloze deletions of the same ID.
- **Smart LaTeX Normalization**: Powered by the bundled `ai-latex-fixer` library for robust math formula rendering.
- **Manual Control**: Generate, show, or regenerate hints with buttons on the card, the review bar, or both.

## Intelligence-Ranked Fallback Hierarchy

The add-on features a multi-tiered, intelligence-driven fallback system. If your primary provider fails (due to rate limits, API key exhaustion, or network issues), the system automatically attempts fallback providers and models strictly ranked by absolute intelligence and reasoning capability.

### Default Provider Priority
1. **Anthropic** (Claude 3.7/3.5 Sonnet)
2. **OpenAI** (GPT-4o)
3. **DeepSeek** (Reasoner/V3)
4. **Grok (xAI)** (Grok 2)
5. **Gemini** (Gemini 2.0 Pro/Flash)
6. **OpenRouter** (Unified Router)
7. **Hugging Face** (Serverless DeepSeek-V3 / Llama 3.3)
8. **Together AI**
9. **Groq**
10. **SambaNova**
11. **NVIDIA**
12. **Mistral**
13. **Cerebras**
14. **Antigravity Proxy** (Embedded Cloud Relay)
15. **Local AI** (Ollama/LM Studio)

---

## Batch Generation & Resumption

The "Local Sequential Queue" is designed for heavy-duty background processing with maximum reliability:

- **Continuous Checkpointing**: The add-on saves its progress to disk (`batch_state.json`) after *every single card* processed. 
- **Accidental Quit Protection**: If you close Anki or it crashes mid-batch, your progress is preserved.
- **Non-Blocking Background Execution**: The process runs in a dedicated background thread, allowing you to study or browse while it works.

---

## Mobile Setup & Troubleshooting

The **Mobile Support** tab allows you to run AI-Hints on mobile devices (AnkiDroid, AnkiMobile, or AnkiWeb) with a premium, responsive layout. 

### ⚡ Getting Started (One-Click Setup)
1. Go to **Tools -> Add-ons -> AI-Hints -> Config -> Mobile Support**.
2. Click **One-Click Install: Setup All Note Types**. (This inserts the safe injection tags into your templates and copies the modern `_ai_hints_template.js` script to your media folder automatically).
3. **Sync Anki on PC** to upload the fresh template script to AnkiWeb.
4. **Sync AnkiDroid/AnkiMobile** on your phone to download the new files.

### ⚠️ Troubleshooting AnkiDroid Cache (WebView)
If you have recently updated the add-on and still see the old card style, duplicate labels (e.g., `AI Hints:`), or missing buttons on **AnkiDroid**, it is because Android's internal WebView aggressively caches local JavaScript files.

To force AnkiDroid to load the new script:
1. **Sync AnkiDroid** to ensure all files are downloaded.
2. **Force-Close the App**: Swipe AnkiDroid away from your phone's **Recent Apps** list. This terminates the persistent WebView session and clears the cache.
3. **Reopen AnkiDroid**: Open the app and review a card. The clean desktop-style UI will render perfectly.

### 🧹 Clean Uninstallation
If you want to remove AI-Hints from mobile:
1. Go to the **Mobile Support** tab and click **Remove from All Note Types**.
2. This will instantly strip the injection code from all templates, **automatically delete the `_ai_hints_template.js` file** from your media folder, and trigger a sync to push the cleanup to AnkiWeb in a single click!

---

## Configuration

Go to **Tools -> Add-ons -> AI-Hints -> Config** to open the graphical configuration window.

- **General Tab**: Select your provider, MCQ options count, and storage mode.
- **AI Providers Tab**: Enter API keys, change models, or configure custom endpoints.
- **Mobile Support Tab**: Smart one-click installer for AnkiDroid/AnkiMobile with Emoji mode settings.
- **Advanced Tab**: System prompts, Note Type field selectors, and Raw JSON Editor.

## Get Your API Keys

- **Google Gemini**: [aistudio.google.com](https://aistudio.google.com/app/apikey)
- **Groq**: [console.groq.com](https://console.groq.com/keys)
- **SambaNova**: [cloud.sambanova.ai/apis](https://cloud.sambanova.ai/apis)
- **Hugging Face**: [huggingface.co](https://huggingface.co/settings/tokens)
- **OpenRouter**: [openrouter.ai](https://openrouter.ai/keys)
- **OpenAI**: [platform.openai.com](https://platform.openai.com/api-keys)
- **Anthropic**: [console.anthropic.com](https://console.anthropic.com/)

---

> `ai-latex-fixer` is included as a Git submodule at `addon/latex_fixer/`. When cloning for development, run `git submodule update --init` to pull it.

## Development

See [DEVELOPMENT.md](DEVELOPMENT.md) for build instructions and technical details.
[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/D1D01W6NQT)

## License

MIT

<img width="2083" height="1188" alt="Screenshot_20260507_215546" src="https://github.com/user-attachments/assets/b3b54ab4-fefb-44cf-85c4-3cf02b7cbe88" />
<img width="1117" height="1073" alt="Screenshot_20260507_215620" src="https://github.com/user-attachments/assets/02e4401e-acf4-4669-88d2-76c28f007d26" />
<img width="1117" height="1189" alt="Screenshot_20260507_215646" src="https://github.com/user-attachments/assets/84404bbc-3316-4dc6-ba9a-51e129589aca" />
<img width="1117" height="1189" alt="Screenshot_20260507_215709" src="https://github.com/user-attachments/assets/0d41d057-0ca9-4415-b5c9-5a09a19c0798" />
<img width="1117" height="1189" alt="Screenshot_20260507_215713" src="https://github.com/user-attachments/assets/51dc0bba-234e-4a9b-a2cb-638cb7b17e08" />
Mobile support (AnkiDroid and AnkiMobile) is achieved through a “Zero-Addon” architecture. This means that while the Desktop requires the Python addon to generate data, the mobile devices only need the data itself and a lightweight JavaScript renderer to display it.

<img width="337" height="750" alt="image" src="https://github.com/user-attachments/assets/1965d9f5-c353-423d-8721-c7581aecae82" />


## Changelog

### May 24, 2026 (v2.5.1)
- **Anki Terminator Integration**: Added monkey-patch support for the "Anki Terminator" add-on. Intercepts card text field access and sanitizes AI-Hints hidden divs and container markup, ensuring seamless co-existence without UI disruption.
- **Strict Field Extraction**: Restructured card content parsing to strictly target standard Front/Back fields for standard/reversed card extraction, ensuring auxiliary/storage fields are not sent to the LLM.
- **Robust Template Detection**: Refactored front field detection to robustly match field references containing spaces or filters (like `{{type:Back}}` or `{{ Back }}`).

### May 23, 2026
- **Flicker-Free UI**: Re-engineered the template rendering engine to be fully idempotent. Eliminated the annoying "flash" and intermittent click failures by preventing redundant DOM reconstructions during card transitions and state updates.
- **Enhanced Cloze Support**: Added support for `c2`/`c3` keyed hints, allowing independent AI hints for different cloze deletions on the same note.
- **Improved UI Layout**: Refactored the configuration dialog's "General" tab to prevent layout squishing and improved the visual polish of the reviewer buttons with smoother transitions and animations.
- **PyQt6 Compatibility**: Updated internal dialog execution calls for better compatibility with modern Anki versions.
- **Reversed Template Fix**: Corrected front/back detection for "Basic (and reversed card)" templates to ensure hints are generated for the correct face.
- **Unicode Stability**: Fixed potential `UnicodeDecodeError` when reading addon metadata.
- **Smart Render Guards**: Added protection against re-rendering while editing fields and implemented more aggressive stale data pruning.

### May 21, 2026
- **Log Viewer Decoding Fix**: Added `errors="replace"` to the log file reading logic in the configuration dialog to prevent Anki from raising a `UnicodeDecodeError` when logs contain invalid UTF-8/ANSI characters.
- **Crash Fix**: Resolved a `TypeError` crash in `CardParser.__init__` caused by obsolete configuration arguments (`target_fields` and `note_type_fields`).
- **Robust Note Updates**: Updated note saving logic to use `mw.col.update_note(note)` instead of the deprecated `note.flush()` method to ensure database consistency.
- **Enhanced Data Extraction**: Implemented robust field-scanning extraction methods for the migration utility.
- **First Field Storage Priority**: Forced AI hints storage to the first field of all cards (improving front-side card rendering compatibility).
- **Data Migration Tool**: Added a dedicated migration utility in the config dialog to scan, clean, and move all existing AI hints to the first fields of notes safely with progress and stop/resume controls.
- **Card Shuffling Fix**: Ensured the correct answer option is tracked through the shuffle logic.
- **Reviewer Refresh Races**: Resolved races in reviewer AI hints refresh logic.
- **Data Ghosting Resolution**: Restored multi-block rendering to completely resolve Web-review card data ghosting.

### May 19, 2026
- **Optimized Startup**: Delayed heavy initialization of the Antigravity Proxy and Mobile Sync to prevent resource contention and potential crashes during Anki startup.
- **Resource Efficiency**: Replaced the heavy `AnkiWebView` used for the Ko-fi widget with a native `QPushButton` to reduce memory overhead and improve UI responsiveness.
- **Stable Update Notifications**: Added a delay to automatic support dialog popups after updates and fixed the tab index to correctly open the "Support Authors" tab.
- **Cross-Platform Keyboard Shortcuts**: Implemented review screen keyboard shortcuts for both Desktop (native python hook) and Mobile/Standalone (JavaScript keydown listener).
- **Customizable Default Mappings**: Swapped default toggle mappings so `Alt+2` toggles hints and `Alt+3` toggles options.

### May 18, 2026
- **Offline Template Resolution**: Corrected a major bug where template installers injected prompt fields instead of storage fields, enabling full offline card reviewer button rendering.
- **Propagation & Tap Delay Prevention**: Restructured `template.js` reviewer buttons to block event propagation (`e.stopPropagation()` / `e.preventDefault()`), eliminating click delays and double-clicking issues.
- **Python 3.14 exit-crash prevention**: Cleaned timers and shutdown daemon in `profile_will_close` hook to stop PyQt6/sip crash.
- **Self-Healing Daemon Startup**: Automatically kills previous session's zombie proxy process on start to release Port 3000 conflicts.
- **Polished Card UI**: Hidden 'Clear' buttons offline/mobile, and unconditionally hidden duplicate static HTML blocks to ensure styling parity.
- **Critical Stability Fix**: Implemented a singleton guard in the UI script to prevent multiple instances from running simultaneously, resolving reported crashes in Anki's web engine (SIGABRT).
- **Reduced Rendering Overhead**: Removed redundant re-render triggers in the backend to improve performance and reduce UI flickering.
- **Unified UI System**: Desktop and Mobile now share the exact same rendering engine (`template.js`), ensuring consistent features (like shuffling and MathJax) across all devices.
- **Smart Auto-Updates**: Once you click "One-Click Install", the addon automatically keeps your mobile script and templates up to date whenever you update the addon or change settings.
- **Compact Emoji Mode**: Optional ultra-compact UI for mobile that uses pure emojis (💡, 🎯, 🗑️) instead of text labels.
- **Edit Field Compatibility**: Improved compatibility with "Edit Field During Review Native" — UI updates now pause while you are typing to prevent focus loss.
- **Robust Clearing**: Re-engineered the "Clear" logic to be HTML-aware, aggressively removing redundant `<br>` tags and empty lines to keep your cards perfectly clean.
- **Improved Navigation**: Added separate "Save", "Save & Close", and "Cancel" buttons to the configuration dialog.
- **Performance**: Optimized rendering and state management to eliminate "ghost data" and flickering during card transitions.

### May 13, 2026
- **Improved Pre-generation Strategy**: Implemented smarter queue-peeking for Anki v3 scheduler.
- **Robust Network Monitoring**: Added background network status monitor.
- **Global Emergency Stop**: Added instant-kill signal for all AI generations.
- **Optimized Provider Failover**: Enhanced 404/Timeout recovery.
- **Missing Cloze Handling**: Graceful detection and skipping for cards with missing clozes.

### May 12, 2026
- **Persistent Model Blacklisting**: Failures now persist across restarts via `blacklist.json`.
- **Enhanced Fallback UI**: Dedicated fallback manager with testing buttons.
- **Instant-Open Config UI**: Lazy-loading for note types and fields.
- **Optimized Anki Startup**: Deferred background tasks.
- **Interactive Model Testing**: Instant connectivity verification in config.
