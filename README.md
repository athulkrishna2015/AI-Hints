# AI-Hints Anki Add-on

AI-Hints is a powerful Anki add-on that uses Artificial Intelligence to generate helpful hints or multiple-choice options for your flashcards during review. It helps simulate real exam conditions by including the correct answer alongside plausible distractors even for open-ended cards.

Install from [anki web ](https://ankiweb.net/shared/info/2119980872)

github:[https://github.com/athulkrishna2015/AI-Hints](https://github.com/athulkrishna2015/AI-Hints)
## Features

- **Multi-Provider Support**: Supports OpenAI, Anthropic, Gemini, Groq, DeepSeek, NVIDIA, Mistral, Grok, OpenRouter, **Together AI**, **Hugging Face**, **SambaNova**, **Cerebras**, and any OpenAI-compatible local API (like Ollama or LM Studio).
- **Automatic Fallback**: If your primary AI provider fails (e.g., rate limits or API downtime), the add-on automatically attempts to generate hints using your next provider. The fallback order is strictly ranked by absolute intelligence (smartest-first).
- **Smart Key Guard**: The fallback system only queries providers where you have configured a valid API key (or enabled local endpoints). Any unconfigured providers are safely and silently skipped.
- **Model Fallbacks**: Each provider has its own **intelligence-ranked fallback hierarchy** (smartest-first) to automatically retry next-best models before switching to a different provider.
- **Multi-Cloze Support**: Optimized for cards with multiple cloze deletions of the same ID (e.g., `{{c1::A}} ... {{c1::B}}`). The AI now generates coordinated options (e.g., `A, B`) for these complex cards.
- **Improved UI Stability**: Hints and options now consistently persist through the "Show Answer" transition and are only cleared when moving to a new card.
- **Smart LaTeX Normalization**: Advanced math repair logic that handles nested delimiters, bare commands (like `sum` or `infty`), and multi-part mathematical expressions.
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
- **MathJax-Aware Rendering**: AI-Hints prioritizes standard LaTeX/MathJax delimiters. It strictly uses `\( ... \)` for inline math and `\[ ... \]` for block math, explicitly avoiding `$ ... $` or `$$ ... $$` to ensure compatibility with all Anki platforms. It preserves and repairs common LaTeX/MathJax output, including escaped JSON backslashes and bare variables such as `lambda_L`.
- **Field Customization**: Specify exactly which fields to send to the AI for each note type. Optimized for Cloze cards by default.
- **Target Fields**: Configure a global fallback list of fields where the AI-Hints block should be stored.
- **MathJax Format Control**: Switch between standard LaTeX delimiters `\( ... \)` and inline `$...$` depending on your preference.
- **Persistent Storage**: Generated hints are saved directly in your card's fields (e.g., "Extras" or "Back"), so they work on AnkiMobile and AnkiDroid too.
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
14. **Local AI** (Ollama/LM Studio)

### Model Fallback Rankings
For individual providers, if the default model fails, it retries using the smartest available models first:
* **OpenRouter**: `anthropic/claude-3.5-sonnet` ➡️ `openai/gpt-4o` ➡️ `deepseek/deepseek-chat` ➡️ `meta-llama/llama-3.3-70b-instruct` ➡️ `meta-llama/llama-3.3-70b-instruct:free` ➡️ `google/gemini-2.0-flash-001`
* **Gemini**: `gemini-2.0-pro-exp-02-05` ➡️ `gemini-1.5-pro` ➡️ `gemini-2.0-flash` ➡️ `gemini-1.5-flash`
* **Anthropic**: `claude-3-7-sonnet-latest` ➡️ `claude-3-5-sonnet-latest` ➡️ `claude-3-5-haiku-latest`
* **OpenAI**: `gpt-4o` ➡️ `o1-mini` ➡️ `gpt-4o-mini`

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

### 1.1.3
- **Unified Model Names & Fallback Priority**: Consolidated both sections into a single, beautiful, and intuitive reorderable layout with solid unicode arrow buttons (`▲`/`▼`) for perfect, high-DPI scaling rendering.
- **Advanced System Prompt**: Redesigned the baseline system prompt with clean Markdown headings and stricter formatting rules to enforce raw, markdown-free JSON and distractor uniformity.
- **Webview Persistence Clear**: Fixed the "Clear AI-Hints cached data" action to completely wipe the card's webview persistent memory cache, instantly removing old hints from the screen.
- **Review UX Stability**: Completely isolated database interactions from Anki's undo stack, restoring the original stable card-refreshing logic.

### 1.1.2
- **Multi-Cloze Support**: Hints and options for each cloze deletion are now stored independently under distinct keys (`c1`, `c2`, etc.) inside a single unified JSON block to prevent data collisions.
- **Improved Math Repair**: Refined `latex_fixer` to gracefully handle dangling LaTeX delimiters (like single trailing `$`) and improved math wrapping for complex expressions containing `\mathbf` or `\text{}`.
- **Option Deduplication**: Enforced mathematically and conceptually unique option generation at both prompt and code level.
- **Automatic Reveal Prevention**: Ensured hints and options strictly remain hidden on return visits and card navigation, requiring manual button press for review.

### 1.1.1
- **UI Performance Optimization**: Significant reduction in UI lag during deck navigation by implementing web asset caching and optimizing background task timeouts.
- **Persistent Settings Fix**: Resolved a long-standing issue where the active AI provider would reset to default on every restart.
- **New Configuration Options**: Added **MathJax Format** (delimiters vs. inline) and **Target Fields** (global fallback for hint storage) to the Advanced UI.
- **Robust Math Repair**: Enhanced the LaTeX fixer to catch and repair common AI hallucinations like `\ninfty` (rendered as $\ni$ nfty) and "sum from... to infinity" in plain text.
- **Model Maintenance**: Updated decommissioned model IDs for Groq and Cerebras to ensure zero-downtime fallback.

### 1.1.0
- **Standardized LaTeX Pipeline**: Transitioned to dollar-based (`$`/`$$`) AI generation for maximum model reliability, with automatic normalization to Anki-compatible delimiters.
- **Enhanced MCQ Reliability**: Implemented a double-layered deduplication system (prompt-level + post-normalization code validation) to ensure all multiple-choice options are unique and conceptually distinct.
- **LaTeX Fixer 2.0**: Massive overhaul of the internal `ai-latex-fixer` library, now achieving 100% pass rate on the regression test suite.
- **Improved Spacing**: Refined logic for spacing around math blocks and punctuation to prevent layout jitters.

### 1.0.6
- **Multi-Cloze Support**: Added specialized handling for cards containing multiple cloze deletions with the same ID.
- **Stability Improvements**: Fixed an issue where hints would "disappear" after pressing "Show Answer" due to stale card rendering.
- **Enhanced LaTeX Fixer**: Improved the `ai-latex-fixer` library to handle nested delimiters (e.g., `\(\infty\)` inside larger blocks) and better standardize multi-part math strings.
- **Aggressive Hiding**: Ensured hints and options stay strictly hidden on existing cards until manually revealed or just generated.

### 1.0.5
- **Bug Fixes**: Improved handling of nested LaTeX delimiters and double-escaped backslashes in AI responses.
- **Performance**: Optimized card parsing for complex Cloze notes.

### 1.0.4
- **Enhanced Logging**: Logs now show the specific model name being queried for every request.
- **Advanced Log Filtering**: Added a real-time search box to the Logs tab to filter entries by keyword (e.g., model name, provider, or error).
- **Bug Fixes**: Improved handling of nested LaTeX delimiters and double-escaped backslashes in AI responses.

### 1.0.3
- **Dynamic Model Discovery**: Added "Fetch" and "Fetch All" buttons to retrieve the latest models directly from AI provider APIs.
- **Customizable Fallback Priority**: New drag-and-drop list to set the preferred order for provider fallbacks.
- **UI Upgrade**: Replaced model name text fields with editable dropdowns containing popular model suggestions.
- **Smarter Defaults**: Updated default models to `gemini-2.0-flash-exp` (Gemini), `llama-3.3-70b-versatile` (Groq), and `google/gemini-2.0-flash-exp:free` (OpenRouter).

### 1.0.2
- **LaTeX Instruction Refinement**: Updated system prompts to strictly require `\(` and `\[` delimiters and explicitly forbid `$` signs.
- **MathJax-Aware Rendering**: Improved preservation and repair of common LaTeX output patterns.

### 1.0.0
- **Initial Release**: Multi-provider support with automatic fallback and persistent hint storage.
- **MathJax Support**: Core logic for handling LaTeX/MathJax in AI-generated hints and options.
- **Live Log Viewer**: Real-time debugging interface in the configuration dialog.
