# AI-Hints Anki Add-on

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/D1D01W6NQT)

AI-Hints is a powerful Anki add-on that uses Artificial Intelligence to generate helpful hints or multiple-choice options for your flashcards during review. It helps simulate real exam conditions by including the correct answer alongside plausible distractors even for open-ended cards.

Install from [anki web ](https://ankiweb.net/shared/info/2119980872)

github:[https://github.com/athulkrishna2015/AI-Hints](https://github.com/athulkrishna2015/AI-Hints)

## Features

### 🔌 Multi-Provider AI Engine
- **Broad Provider Support**: Supports OpenAI, Anthropic, Gemini, DeepSeek, Grok (xAI), Groq, OpenRouter, NVIDIA, Mistral, SambaNova, Cerebras, Hugging Face, Together AI, and any local API (Ollama/LM Studio).
- **Intelligence-Ranked Fallbacks**: Automatically retries using next-best models, alternative API keys, or entirely different providers in case of rate limits or failures.
- **API Key Rotation**: Rotate and prioritize multiple API keys per provider, with visual toggle controls and disk-persistent failure-based key blacklisting.

### 🎮 Interactive MCQ & Review UI
- **Interactive Option Selection**: Select MCQ options on the front side (via click, tap, or hotkeys `1-9`) and automatically flip to see color-coded results (green for correct, red for incorrect).
- **Auto-Rating Integrations**: Enable auto-rating to instantly rate a card `Good` (on correct option) or `Again` (on incorrect option) after selecting an MCQ option, with full undo protection.
- **Inline Editor**: Hold `Ctrl`/`Cmd` during review and click any hint or option text block to edit it inline. Changes save directly to the card database and cache instantly.
- **Factual Error Warnings**: Automatically highlights factual errors in card content with a dedicated warn alert explaining the error and the correct fact.
- **Smart LaTeX Normalization**: Uses the bundled `ai-latex-fixer` library for robust math formula rendering and delimiter alignment.

### ⚡ Generation & Note Management
- **Queued Batch Jobs**: Queue multiple batch generation runs, monitor active jobs, reorder/cancel pending jobs, and automatically resume queues after Anki restarts.
- **Smart Auto-Regeneration**: Auto-refresh generated hints when the note is edited, when stored metadata is older than a target version, or when it predates a target date.
- **Bulk Controls**: Easily bulk skip or unskip whole decks or selected card groups directly from the Anki browser and sidebar menus.
- **Multi-Cloze Alignment**: Supports cards with multiple cloze deletions, separating answers cleanly using a semicolon (` ; `) delimiter.


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

- **General Tab**: Select your default provider, MCQ options count, database storage mode, and auto-generation rules including modified-card, version, and generation-time based regeneration.
- **AI Providers Tab**: Unified settings where each provider is grouped into a clean card layout containing its API Key (with eye visibility 👁️ toggles), active model selection, Up/Down priority sorting, dynamic fetch and test features, and checkbox toggles to **completely disable fallbacks** to specific providers.
- **Mobile Support Tab**: Smart one-click installer for AnkiDroid/AnkiMobile with Emoji mode settings.
- **Shortcuts Tab**: Customize AI-Hints action keys and the modifier used on the answer side. The front side also accepts the action keys without the modifier for faster review.
- **Advanced Tab**: Customize your system prompt, tune active-review and pregeneration API request timeouts, migrate hints inside your collection, use maintenance cleanups (now with **Searchable Deck Scoping**), hide visible hint boxes with the **HTML to JSON tool**, edit raw JSON configs, and manage the **Model Cooldowns & Blacklist**.
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
