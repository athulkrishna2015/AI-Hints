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

## Changelog

### May 18, 2026 (Patch v2.3.1)
- **Critical Stability Fix**: Implemented a singleton guard in the UI script to prevent multiple instances from running simultaneously, resolving reported crashes in Anki's web engine (SIGABRT).
- **Reduced Rendering Overhead**: Removed redundant re-render triggers in the backend to improve performance and reduce UI flickering.

### May 18, 2026 (v2.3.0)
- **Unified UI System**: Desktop and Mobile now share the exact same rendering engine (`template.js`), ensuring consistent features (like shuffling and MathJax) across all devices.
- **Smart Auto-Updates**: Once you click "One-Click Install", the addon automatically keeps your mobile script and templates up to date whenever you update the addon or change settings.
- **Compact Emoji Mode**: Optional ultra-compact UI for mobile that uses pure emojis (💡, 🎯, 🗑️) instead of text labels.
- **Edit Field Compatibility**: Improved compatibility with "Edit Field During Review Native" — UI updates now pause while you are typing to prevent focus loss.
- **Robust Clearing**: Re-engineered the "Clear" logic to be HTML-aware, aggressively removing redundant `<br>` tags and empty lines to keep your cards perfectly clean.
- **Improved Navigation**: Added separate "Save", "Save & Close", and "Cancel" buttons to the configuration dialog.
- **Performance**: Optimized rendering and state management to eliminate "ghost data" and flickering during card transitions.

### May 13, 2026 (v2.2.0)
- **Improved Pre-generation Strategy**: Implemented smarter queue-peeking for Anki v3 scheduler.
- **Robust Network Monitoring**: Added background network status monitor.
- **Global Emergency Stop**: Added instant-kill signal for all AI generations.
- **Optimized Provider Failover**: Enhanced 404/Timeout recovery.
- **Missing Cloze Handling**: Graceful detection and skipping for cards with missing clozes.

### May 12, 2026 (v2.1.0)
- **Persistent Model Blacklisting**: Failures now persist across restarts via `blacklist.json`.
- **Enhanced Fallback UI**: Dedicated fallback manager with testing buttons.
- **Instant-Open Config UI**: Lazy-loading for note types and fields.
- **Optimized Anki Startup**: Deferred background tasks.
- **Interactive Model Testing**: Instant connectivity verification in config.
