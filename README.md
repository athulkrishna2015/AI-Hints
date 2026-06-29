# AI-Hints Anki Add-on

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/D1D01W6NQT)

AI-Hints is a powerful Anki add-on that uses Artificial Intelligence to generate helpful hints or multiple-choice options for your flashcards during review. It helps simulate real exam conditions by including the correct answer alongside plausible distractors even for open-ended cards.

Install from [anki web ](https://ankiweb.net/shared/info/2119980872)

github:[https://github.com/athulkrishna2015/AI-Hints](https://github.com/athulkrishna2015/AI-Hints)

## Features

- **Multi-Provider Support**: Supports OpenAI, Anthropic, Gemini, Groq, DeepSeek, NVIDIA, Mistral, Grok, OpenRouter, **Together AI**, **Hugging Face**, **SambaNova**, **Cerebras**, and any OpenAI-compatible local API (like Ollama or LM Studio).
- **Queued Batch Jobs (v4.2.0)**: Start multiple batch generation jobs back-to-back, monitor the active job separately from queued jobs, reorder/cancel pending jobs, and keep progress safely persisted between sessions.
- **Bulk Skip/Unskip Controls (v4.2.0)**: Browser, sidebar, and deck menus now include skip and unskip actions for selected cards or whole groups. Skipping a card clears stale AI hint data and saves only the skipped marker.
- **Inline Editing (v4.0.0)**: Hold `Ctrl` (or `Cmd` on macOS) to highlight any hint or option during review, and click to edit it inline instantly inside a dynamic `<textarea>`. Press `Enter` (without Shift) or blur to save, or `Escape` to cancel. Saves edits directly to the note's JSON block in the database, updates the cache, and updates the webview dynamically with zero page flicker.
- **Unified UI System**: Desktop and Mobile now share the exact same rendering engine (`template.js`), ensuring consistent features (like shuffling and MathJax) across all devices.
- **Optimized Prompt Efficiency (v3.4.1)**: Re-engineered system prompts for maximum token efficiency (~1k tokens saved per request) while improving distractor quality via **Sequential Parallelism**.
- **Granular Key Blacklisting & Gemini 3.5 Flash Support (v3.6.1)**: Refactored key rotation blacklist to block specific model-key-provider combinations rather than entire keys or models. Added support and defaults for Google's new `gemini-3.5-flash` model.
- **Factual Error Warnings & Fixed Pregen Styling (v3.6.0)**: Automatically highlights factual errors in the card content with a dedicated warning indicator explaining why it is wrong and what the correct answer is. Includes polished pregeneration button styling for both light and dark themes.
- **Multiple API Keys Rotation (v3.5.0)**: Supports prioritizing, labeling, and rotating multiple API keys per provider. Includes visual key management (enabling/disabling individual keys) and persistent disk-based key blacklisting.
- **Cross-Platform Support**: Includes a **Unified UI** script that works on AnkiDroid, AnkiMobile, and AnkiWeb even without the add-on installed. Includes a **Smart One-Click Installer** that automatically manages your templates and keep them in sync.
- **Smart Auto-Updates**: Once you've opted-in via the Installer, the addon automatically keeps your mobile setup up to date whenever you update the addon or change settings.
- **Compact Emoji Mode**: Optional ultra-compact UI for mobile that uses pure emojis (💡, 🎯, 🗑️) instead of text labels.
- **HTML-Aware Clearing**: Re-engineered the "Clear" logic to aggressively remove redundant `<br>` tags and empty lines to keep your cards perfectly clean.
- **Edit Field Compatibility**: Improved compatibility with "Edit Field During Review Native" — UI updates now pause while you are typing to prevent focus loss.
- **Automatic Fallback**: If your primary AI provider fails (e.g., rate limits or API downtime), the add-on automatically attempts to generate hints using your next provider.
- **Model Fallbacks**: Each provider has its own **intelligence-ranked fallback hierarchy** to automatically retry next-best models before switching to a different provider.
- **Advanced Global Fallback**: Optionally configure and enable a flat, global priority sequence to mix-and-match fallback models across different providers in any custom order.
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
14. **Local AI** (Ollama/LM Studio)

---

## Batch Generation & Resumption

The batch generation queue is designed for heavy-duty background processing with maximum reliability:

- **Concurrent Multi-Provider Generation**: Leverages multiple AI providers concurrently to process batches significantly faster, with independent fallback queues per provider.
- **Multiple Queued Jobs**: Add another deck, browser selection, or sidebar group while a batch is already running. Pending jobs can be reordered, canceled, or cleared from the Batch tab.
- **Granular Queue Management**: View the next 5 pending cards in the queue directly in the Batch tab status. Includes individual **[✖ Discard]** buttons to surgically remove cards from the current batch.
- **Deck Browser Cogwheel Option**: Start batch generation for any deck directly from the deck browser's options menu.
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

> [!TIP]
> **Quick Script Force-Refresh:** Sometimes after an update, in order to guarantee loading the absolute latest Javascript template, go to **Tools -> Add-ons -> AI-Hints -> Config -> Mobile Support**, first click **Remove from All Note Types** to clean the old assets, and then click **One-Click Install: Setup All Note Types** again to install the fresh script. Then sync your devices.

### 🧹 Clean Uninstallation
If you want to remove AI-Hints from mobile:
1. Go to the **Mobile Support** tab and click **Remove from All Note Types**.
2. This will instantly strip the injection code from all templates, **automatically delete the `_ai_hints_template.js` file** from your media folder, and trigger a sync to push the cleanup to AnkiWeb in a single click!

---

## Configuration

Go to **Tools -> Add-ons -> AI-Hints -> Config** to open the graphical configuration window.

- **General Tab**: Select your default provider, MCQ options count, and database storage mode.
- **AI Providers Tab**: Unified settings where each provider is grouped into a clean card layout containing its API Key (with eye visibility 👁️ toggles), active model selection, Up/Down priority sorting, dynamic fetch and test features, and checkbox toggles to **completely disable fallbacks** to specific providers.
- **Mobile Support Tab**: Smart one-click installer for AnkiDroid/AnkiMobile with Emoji mode settings.
- **Advanced Tab**: Customize your system prompt, migrate hints inside your collection, use maintenance cleanups (now with **Searchable Deck Scoping**), hide visible hint boxes with the **HTML to JSON tool**, edit raw JSON configs, and manage the **Model Cooldowns & Blacklist**.
- **Scrollbar Support**: Smooth scrollbars automatically wrap the Advanced, Mobile, and Batch tabs, ensuring the GUI scales perfectly to fit compact laptops and high-DPI screens.

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

## License

MIT

<img width="2083" height="1188" alt="Screenshot_20260507_215546" src="https://github.com/user-attachments/assets/b3b54ab4-fefb-44cf-85c4-3cf02b7cbe88" />
<img width="1920" height="1025" alt="Screenshot_20260601_002447" src="https://github.com/user-attachments/assets/90a4fea1-bd1d-4dc8-8052-218b017b6131" />
<img width="337" height="750" alt="image" src="https://github.com/user-attachments/assets/1965d9f5-c353-423d-8721-c7581aecae82" />

Mobile support (AnkiDroid and AnkiMobile) is achieved through a “Zero-Addon” architecture. This means that while the Desktop requires the Python addon to generate data, the mobile devices only need the data itself and a lightweight JavaScript renderer to display it.

## Changelog

See [changelog.md](changelog.md) for the full history of changes and releases.
