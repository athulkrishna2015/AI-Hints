# AI-Hints Anki Add-on

AI-Hints is a powerful Anki add-on that uses Artificial Intelligence to generate helpful hints or multiple-choice options for your flashcards during review. It helps simulate real exam conditions by including the correct answer alongside plausible distractors even for open-ended cards.

Install from [anki web ](https://ankiweb.net/shared/info/2119980872)

github:[https://github.com/athulkrishna2015/AI-Hints](https://github.com/athulkrishna2015/AI-Hints)
## Features

- **Multi-Provider Support**: Supports OpenAI, Anthropic, Gemini, Groq, DeepSeek, NVIDIA, Mistral, Grok, OpenRouter, **Together AI**, **Hugging Face**, **SambaNova**, **Cerebras**, **Antigravity Proxy**, and any OpenAI-compatible local API (like Ollama or LM Studio).
- **Native Antigravity Daemon**: Features seamless embedded integration of the [Antigravity Cloud Proxy](https://github.com/frieser/antigravity-proxy). Automatically manages background executable lifecycle, offers one-click account setup dashboard, and provides direct gateway to premier LLMs completely locally.
- **Automatic Fallback**: If your primary AI provider fails (e.g., rate limits or API downtime), the add-on automatically attempts to generate hints using your next provider. The fallback order is strictly ranked by absolute intelligence (smartest-first).
- **Smart Key Guard**: The fallback system only queries providers where you have configured a valid API key (or enabled local endpoints). Any unconfigured providers are safely and silently skipped.
- **Model Fallbacks**: Each provider has its own **intelligence-ranked fallback hierarchy** (smartest-first) to automatically retry next-best models before switching to a different provider.
- **Multi-Cloze Support**: Optimized for cards with multiple cloze deletions of the same ID (e.g., `{{c1::A}} ... {{c1::B}}`). The AI now generates coordinated options (e.g., `A, B`) for these complex cards.
- **Improved UI Stability**: Hints and options now consistently persist through the "Show Answer" transition and are only cleared when moving to a new card.
- **Smart LaTeX Normalization**: Powered by the bundled [`ai-latex-fixer`](https://github.com/athulkrishna2015/ai-latex-fixer) library — a pure-Python engine that handles nested delimiters, missing backslashes, bare math tokens (e.g., `lambda` → `\lambda`), double-escaped backslashes from JSON, Anki `<anki-mathjax>` tags, and multi-part mathematical expressions.
- **Current-Card Hints**: Generated data is scoped to the current card, so cloze deletion and Image Occlusion siblings can each have their own hints/options.
- **Alt-Click Reveal**: Alt-click the current cloze deletion or Image Occlusion mask to reveal only that card's hints/options. Ctrl-click and editable review fields are left alone.
- **Speed Focus Mode Friendly**: Clicking AI-Hints buttons or Alt-click revealing hints restarts the Speed Focus Mode timer when that add-on is installed.
- **Live Log Viewer**: Debug issues in real-time with a built-in log viewer in the config dialog. It features smart scrolling (only scrolls to bottom if you are already there), auto-refresh, and a "Live" status indicator.
- **Improved UI Reset**: Hints and options are now consistently cleared and reset whenever you move to a new card, ensuring a clean state for every review session.
- **Custom AI Support**: Define your own custom endpoints and headers.
- **Universal Compatibility**: Works with Basic, Cloze, Image Occlusion, and custom note types.
- **Smart Shuffling**: Options are shuffled every time you review the card to prevent pattern memorization.
- **Storage Modes**: Choose between **visible HTML** (visible on all devices) or **invisible JSON** (cleaner look, requires add-on to render).
- **Configurable Options**: Set exactly how many MCQ options the AI should generate, including the correct answer (default is 4).
- **Robust JSON Parsing**: Integrates the [`json_repair`](https://github.com/mangiucugna/json_repair) library to gracefully handle malformed AI output (missing quotes, trailing commas, or truncated responses) and recover valid hints.
- **Draggable Fallback Priority**: Reorder your provider priority list directly in the UI — including Antigravity and Local endpoints — by dragging rows up and down.
- **MathJax-Aware Rendering**: AI-Hints repairs common LaTeX/MathJax output, including escaped JSON backslashes and bare variables such as `lambda_L`.
 The default `delimiters` format stores inline math as `\( ... \)` and block math as `\[ ... \]`; the optional `inline` format stores `$ ... $` and `$$ ... $$`.
- **Field Customization**: Specify exactly which fields to send to the AI for each note type. Optimized for Cloze cards by default.
- **Target Fields**: Configure a global fallback list of fields where the AI-Hints block should be stored.
- **MathJax Format Control**: Switch between standard LaTeX delimiters `\( ... \)` and inline `$...$` depending on your preference.
- **Persistent Storage**: Generated hints are saved directly in your card's fields (e.g., "Extras" or "Back"), so they work on AnkiMobile and AnkiDroid too.
- **Cross-Platform Support**: Features a **Unified UI** script that works on AnkiDroid, AnkiMobile, and AnkiWeb even without the add-on installed. Includes a **Smart One-Click Installer** that automatically manages your templates and keep them in sync.

## What's New in v2.3.0

- **Unified UI System**: Desktop and Mobile now share the exact same rendering engine (`template.js`), ensuring consistent features (like shuffling and MathJax) across all devices.
- **Smart Auto-Updates**: Once you click "One-Click Install", the addon automatically keeps your mobile script and templates up to date whenever you update the addon or change settings.
- **Compact Emoji Mode**: Optional ultra-compact UI for mobile that uses pure emojis (💡, 🎯, 🗑️) instead of text labels.
- **Edit Field Compatibility**: Improved compatibility with "Edit Field During Review Native" — UI updates now pause while you are typing to prevent focus loss.
- **Robust Clearing**: Re-engineered the "Clear" logic to be HTML-aware, aggressively removing redundant `<br>` tags and empty lines to keep your cards perfectly clean.
- **Improved Navigation**: Added separate "Save", "Save & Close", and "Cancel" buttons to the configuration dialog.
- **Performance**: Optimized rendering and state management to eliminate "ghost data" and flickering during card transitions.

### Patch v2.3.1

- **Critical Stability Fix**: Implemented a singleton guard in the UI script to prevent multiple instances from running simultaneously, resolving reported crashes in Anki's web engine (SIGABRT).
- **Reduced Rendering Overhead**: Removed redundant re-render triggers in the backend to improve performance and reduce UI flickering.
- **Manual Control**: Generate, show, or regenerate hints with buttons on the card, the review bar, or both.

## Intelligence-Ranked Fallback Hierarchy

The add-on features a multi-tiered, intelligence-driven fallback system. If your primary provider fails (due to rate limits, API key exhaustion, or network issues), the system automatically attempts fallback providers and models strictly ranked by absolute intelligence and reasoning capability.

> [!NOTE]
> The fallback system **only** queries providers where you have entered a valid API key (or enabled local endpoints). Any unconfigured providers are safely and silently skipped.

### Default Provider Priority
When checking fallbacks, providers are queried in the following descending order of reasoning capability:
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

### Model Fallback Rankings
For individual providers, if the default model fails, it retries using the smartest available models first:
* **OpenRouter**: `anthropic/claude-3.5-sonnet` ➡️ `openai/gpt-4o` ➡️ `deepseek/deepseek-chat` ➡️ `meta-llama/llama-3.3-70b-instruct` ➡️ `meta-llama/llama-3.3-70b-instruct:free` ➡️ `google/gemini-2.0-flash-001`
* **Gemini**: `gemini-2.0-pro-exp-02-05` ➡️ `gemini-1.5-pro` ➡️ `gemini-2.0-flash` ➡️ `gemini-1.5-flash`
* **Anthropic**: `claude-3-7-sonnet-latest` ➡️ `claude-3-5-sonnet-latest` ➡️ `claude-3-5-haiku-latest`
* **OpenAI**: `gpt-4o` ➡️ `o1-mini` ➡️ `gpt-4o-mini`

---

## Batch Generation & Resumption

The "Local Sequential Queue" is designed for heavy-duty background processing with maximum reliability:

- **Continuous Checkpointing**: The add-on saves its progress to disk (`batch_state.json`) after *every single card* processed. 
- **Accidental Quit Protection**: If you close Anki or it crashes mid-batch, your progress is preserved. Upon restarting and opening the Batch tab, the add-on will detect the unfinished job and offer a one-click **"Resume Saved Queue"** button.
- **Non-Blocking Background Execution**: Closing the configuration window **does not stop** the batch. The process runs in a dedicated background thread, allowing you to study or browse while it works.
- **Live Status Sync**: Re-opening the configuration window at any time will instantly re-sync and show the current live progress, including the specific model and card ID being processed.

## Generation Priorities

When multiple generation modes are active, the add-on follows a strict hierarchy to ensure your study session remains fast and responsive:

1. **Manual Generation**: Triggered by clicking "Generate" or using a shortcut. Highest priority; clears any active emergency stops.
2. **Auto-Generation**: Automatically starts for new cards or cards with old versions when you show the question.
3. **Pre-generation**: Automatically looks ahead to the *next* card in your queue. To save resources, this **aborts immediately** if a Manual or Auto generation is already running.
4. **Batch Generation**: Runs in a "low-gear" background thread with a 1.5s delay between cards to prevent "hogging" your network or API rate limits.

---

## Configuration

Go to **Tools -> Add-ons -> AI-Hints -> Config** to open the graphical configuration window.

### Configuration Options

- **General Tab**: Select your `ai_provider`, configure the total number of MCQ options (`options_count`), choose whether the Generate button appears on the review card, the review bar, or both, and choose the `storage_mode` (`"json"` for a hidden data block or `"html"` for a visible block).
- **AI Providers Tab**: Enter your `api_keys` for supported providers, change model names, configure a local LLM endpoint (like Ollama), or use the **Custom Providers** section to add, edit, or remove your own API endpoints and custom headers.
- **Local Fallback**: Enable "Use Local AI as fallback" if you want Ollama/LM Studio to be tried after cloud providers fail. Selecting `local` as the active provider always uses the configured local endpoint.
- **Advanced Tab**: 
  - `system_prompt`: The base instructions for the AI.
  - `Note Type Fields`: A graphical dropdown selector that allows you to specify exactly which fields should be sent to the AI for each of your specific note types.
  - `Raw JSON Editor`: Advanced users can edit the full config directly; when the raw editor is enabled, it is saved as the source of truth.

## Get Your API Keys

To use this add-on, you need an API key from one of the supported providers.

### Free / Freemium Providers (No credit card required)
- **Google Gemini**: [aistudio.google.com](https://aistudio.google.com/app/apikey)
- **Groq**: [console.groq.com](https://console.groq.com/keys)
- **SambaNova**: [cloud.sambanova.ai/apis](https://cloud.sambanova.ai/apis)
- **Cerebras**: [cloud.cerebras.ai](https://cloud.cerebras.ai/)
- **Hugging Face**: [huggingface.co](https://huggingface.co/settings/tokens)
- **OpenRouter**: [openrouter.ai](https://openrouter.ai/keys) (Offers many $0/token models)
- **Antigravity Cloud Proxy**: [Embedded Plugin](https://github.com/frieser/antigravity-proxy) (No credit card, internal account rotation)
- **Ollama (Local AI)**: [ollama.com](https://ollama.com/) (No API key or internet required)

### Paid Providers
- **OpenAI**: [platform.openai.com](https://platform.openai.com/api-keys)
- **Anthropic (Claude)**: [console.anthropic.com](https://console.anthropic.com/)
- **DeepSeek**: [platform.deepseek.com](https://platform.deepseek.com/api_keys)
- **Together AI**: [api.together.xyz](https://api.together.xyz/settings/api-keys) (Requires initial deposit)
- **Mistral**: [console.mistral.ai](https://console.aimistral.ai/api-keys/)
- **Grok (xAI)**: [console.x.ai](https://console.x.ai/)
- **NVIDIA**: [build.nvidia.com](https://build.nvidia.com/explore/discover)

### Example Config (Advanced Users):
You can also use the **Raw JSON Editor** in the Advanced tab if you prefer editing JSON directly:
```json
{
    "ai_provider": "openai",
    "storage_mode": "json",
    "options_count": 4,
    "api_keys": {
        "openai": "sk-...",
        "groq": "gsk_...",
        "sambanova": "",
        "cerebras": ""
    },
    "models": {
        "gemini": "gemini-3-flash-preview",
        "groq": "llama-3.1-8b-instant",
        "openrouter": "meta-llama/llama-3.1-8b-instruct"
    },
    "model_fallbacks": {
        "gemini": ["gemini-3.1-flash-lite-preview"],
        "groq": ["llama-3.3-70b-versatile"]
    },
    "local_endpoint": {
        "enabled": false,
        "base_url": "http://localhost:11434/v1",
        "model": "llama3",
        "api_key": ""
    },
    "note_type_fields": {
        "Cloze": ["Text"],
        "Basic": ["Front", "Back"]
    },
    "custom_providers": {
        "my-local-llm": {
            "url": "http://localhost:8080/v1/chat/completions",
            "api_key": "optional",
            "model": "mistral-7b",
            "headers": {
                "X-Custom-Header": "value"
            }
        }
    }
}
```

## Open Source Components

This add-on bundles the following open source libraries as Git submodules:

| Library | Purpose | License |
|---|---|---|
| [`ai-latex-fixer`](https://github.com/athulkrishna2015/ai-latex-fixer) | Pure-Python LaTeX/MathJax repair engine for LLM output. Fixes missing backslashes, mixed delimiters, nested tags, double-escaped JSON, and bare math tokens. | MIT |
| [`json_repair`](https://github.com/mangiucugna/json_repair) | Recovers and parses malformed JSON from AI responses (missing quotes, trailing commas, truncated output). | MIT |

> [!NOTE]
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


## Changelog

### May 13, 2026 (v2.2.0)
- **Improved Pre-generation Strategy**: Implemented a smarter queue-peeking algorithm that scans the top 5 cards to reliably identify the next card needing hints, even when the current card is still marked as queued by Anki's v3 scheduler.
- **Robust Network Monitoring**: Added a background network status monitor that prevents AI providers from being blacklisted during general internet outages, ensuring faster recovery once back online.
- **Global Emergency Stop**: Added an instant-kill signal to immediately terminate all active AI generations across the entire add-on.
- **Optimized Provider Failover**: Enhanced the failover logic to instantly break the model retry loop on 404/Timeout errors, enabling faster switching to backup providers.
- **Missing Cloze Handling**: Added graceful detection and skipping for cards with missing cloze deletions, preventing "no content found" errors during batch processing and pre-generation.
- **UI & UX Refinement**:
  - Relocated the "Stop All" button to the bottom action bar for better accessibility.
  - Fixed UI layout stretching issues in the General configuration tab.
  - Added a "Pre-generation" source filter to the Live Log Viewer.
- **Technical Integrity**: Updated the internal test suite to verify queue peeking, missing cloze logic, and pre-generation cycles.

### May 12, 2026 (v2.1.0)
- **Persistent Model Blacklisting**: Model failures, rate limits, and quota exhaustion states now persist across Anki restarts via a local `blacklist.json` file.
- **Enhanced Fallback UI**:
  - Added a dedicated **[Fallbacks]** button for every AI provider in the configuration tab.
  - Implemented a new priority manager dialog to manually reorder and prioritize fallback models.
  - Integrated **[Test]** buttons directly inside the fallback selector to verify model connectivity before adding them to your list.
- **Improved Failover Logic**: Removed the "Trying anyway" bypass to ensure blacklisted models are strictly skipped, allowing faster failover to working providers.
- **Robust Rate-Limit Recovery**: Blacklist entries are now automatically cleared if a model succeeds during a manual test, allowing instant recovery without waiting for the cooldown timer.
- **Clean Packaging**: Updated build exclusions to ensure local cache files (`blacklist.json`, `batch_state.json`) are never included in the distributed `.ankiaddon` package.
- **Major Performance & UX Overhaul**: Comprehensive optimization of the addon's core lifecycle and configuration interface.
- **Instant-Open Config UI**: Implemented lazy-loading for note types and fields, reducing configuration window opening time from seconds to milliseconds.
- **Optimized Anki Startup**: Background tasks (proxy daemon startup, log clearing) are now deferred until after the profile is loaded, ensuring Anki reaches the main screen instantly.
- **Interactive Model Testing**: Added "Test" buttons next to every AI provider. Instantly verify your API keys, connectivity, and generation quality with a real-world test prompt before saving.
- **Live Proxy Status Indicator**: Added a real-time, color-coded status tracker (**● Running** / **○ Stopped**) for the Antigravity Proxy daemon in the configuration tab.
- **Intelligent Dropdown Synchronization**: The "Active AI Provider" and individual "Model" dropdowns now strictly follow your custom priority order and the backend's intelligence-ranked fallback hierarchy.
- **Python 3.14 Compatibility**: Fixed a startup crash caused by legacy hook names in the latest Python/Anki builds.
- **Proxy Manager Stability**: Resolved an `UnboundLocalError` that could prevent the Antigravity daemon from starting on certain platforms.

### May 12, 2026 (v1.6.1)
- **ai-latex-fixer Submodule**: Extracted the LaTeX normalization engine into a standalone, reusable open source library at [`ai-latex-fixer`](https://github.com/athulkrishna2015/ai-latex-fixer). Bundled as a Git submodule for clean versioning and independent development.
- **Draggable Fallback Priority for All Providers**: Antigravity and Local endpoints can now be freely reordered within the Provider Priority drag list alongside standard cloud providers.
- **Config Modularization**: Split the monolithic 2,150+ line config UI into 10 focused files using Python multiple-inheritance Mixin architecture for maintainability.
- **Freeze Fix**: Resolved Anki freeze-on-config-open caused by synchronous log file I/O during dialog construction.
- **Tools Menu Entry Restored**: Re-added `Tools → AI-Hints Config` menu shortcut that was accidentally dropped during refactoring.
- **`bin/config.json` Now Tracked**: Fixed `.gitignore` to correctly track the proxy daemon's static config while still excluding binaries and account secrets.

### May 12, 2026 (v1.6.0)
- **Native Antigravity Proxy Daemon**: Directly bundles the standalone Antigravity Cloud Proxy in optimized binary format. Eliminates `Bun` node dependencies completely for end-users.
- **Zero-Config Lifecycle Manager**: Custom-built background process daemon seamlessly handles automatic launch, graceful cleanup on exit, and live port conflict mitigation.
- **Smart Binary Auto-Downloader**: Implemented iterative binary caching. The addon dynamically downloads only the exact binary for the host OS (Windows / Mac M1 / Mac Intel / Linux) on first use, dramatically slashing installer zip bloat by 200MB+.
- **Real-time Visual Downloader UX**: Features dynamic PyQt speed calculators, total file percentages, live estimated time indicators (ETA), and safe cancellation callbacks.
- **Hot-Reload Live Saves**: Hooked the configuration writer to execute hot restarts. Enabling, disabling, or starting the proxy happens live immediately upon save—**Zero Anki restarts required.**
- **Dedicated Launch Console**: Introduced the [🚀 Open Setup Dashboard] widget enabling instant account configuration directly inside your native browser.

### May 12, 2026 (v1.5.0)
- **Native Gemini Batch Generation**: Full support for async Batch API execution. Push up to 1,000 cards per batch and let it generate offline!
- **Dedicated Batch Dashboard**: New "Batch Generation" tab in Config settings. Monitor pending jobs in real-time and trigger deck-wide queuing.
- **Seamless Native Deck Selection**: Injected Anki's official `DeckChooser` widget directly into the configuration panel for guaranteed stable, ultra-fast hierarchical searching.
- **Modeless UI Autonomy**: Severed parent links between the Config window and Add-on Manager; you can now freely study, minimize, and navigate Anki with config open.
- **Dynamic Cross-Gemini Failover**: Restored intelligent failover redundancy; hitting specific limits on one Gemini model now naturally advances to available sibling backups.
- **Batch Version-Gating**: Injected granular version controls into the batch generator, allowing automated mass-upgrades of legacy cards while skipping up-to-date assets.
- **High-Reliability Matching**: Enhanced backend-driven answer state flags to correctly highlight correct options, bypassing custom template flaws.
- **Robust Latex Normalization**: Standardized options comparison logic so LaTeX variances like `$$` vs `\(` never cause highlight mismatches.
- **Clean-State Startup Recovery**: Patched non-standard library imports guaranteeing 100% load health across high-strictness environments.

### May 11, 2026 (v1.4.1)
- **Gemini 3 Native Integration**: Restored full compatibility for `gemini-3` preview models.
- **Explicit Thinking Configuration**: Leverages new `thinkingConfig` to maximize logical reasoning fidelity.
- **Correct Answer Highlighting**: Automatically identifies and highlights correct options on the back side of the card.
- **Version-Gated Auto Regeneration**: Automatically updates legacy card hints based on configured add-on version gates.
- **Configurable UI Extensions**: Added customizable global keyboard shortcuts and granular auto-reveal triggers.
- **Modeless Config Windows**: Transitioned configuration views to modeless UI widgets to allow concurrently deck browsing.
- **Smart Stability Patches**: Disabled aggressive LaTeX fixes by default and added dynamic offline status animations.

### May 9, 2026 (v1.3.0)
- **Robust JSON Parsing Layer**: Vendored the [`json_repair`](https://github.com/mangiucugna/json_repair) engine and added hallucination filters to sanitize AI output strings.
- **Asynchronous Generation**: Fully threaded backend processing to completely eliminate review lag and interface blocking.
- **Native Undo Integration**: Hooked into Anki storage caches for zero-latency real-time synchronization on **Ctrl+Z**.
- **Dynamic UI Rendering**: Re-architected HTML display loops to render and scale assets instantly without delay.
- **Intelligent Option Sanitation**: Added fully automated prefix stripping (`Answer:`, `Distractor:`) and option deduplication logic.
- **Interactive Failovers**: Streamlined the fallback manager UI to permit unicode-based reordering of preferred providers.

### May 8, 2026
- **Multi-Cloze Independent Keying**: Partitioned JSON storage to isolate and track hint data distinct for each cloze key (`c1`, `c2`, etc.).
- **Standardized LaTeX Pipelines**: Standardized the default generator prompt to rely on highly-stable dollar (`$`) formats.
- **Intelligent Math Repair**: Integrated robust regex libraries to correct hanging LaTeX delimiters and common AI escaped chars.
- **Front-Side Persistence Stability**: Resolved issues where DOM updates mistakenly purged dynamic hint elements during state loads.

### May 7, 2026
- **Initial Release**: Robust cross-provider support featuring automatic failover chains and persistent on-disk storage.
- **Live Trace Visualization**: Built-in trace console console enabling deep visibility into background worker API payloads.
- **Dynamic Model Discovery**: Enabled "Fetch" retrieval to ingest global endpoints directly from active AI service accounts.
