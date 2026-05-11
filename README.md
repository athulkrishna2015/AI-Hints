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
- **Robust JSON Parsing**: Integrates the `json_repair` library to gracefully handle malformed AI output (missing quotes, trailing commas, or truncated responses) and recover valid hints.
- **MathJax-Aware Rendering**: AI-Hints repairs common LaTeX/MathJax output, including escaped JSON backslashes and bare variables such as `lambda_L`.
 The default `delimiters` format stores inline math as `\( ... \)` and block math as `\[ ... \]`; the optional `inline` format stores `$ ... $` and `$$ ... $$`.
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

### May 11, 2026
- **Gemini 3 Native Integration**: Restored full compatibility for `gemini-3` preview models.
- **Explicit Thinking Configuration**: Leverages new `thinkingConfig` to maximize logical reasoning fidelity.
- **Correct Answer Highlighting**: Automatically identifies and highlights correct options on the back side of the card.
- **Version-Gated Auto Regeneration**: Automatically updates legacy card hints based on configured add-on version gates.
- **Configurable UI Extensions**: Added customizable global keyboard shortcuts and granular auto-reveal triggers.
- **Modeless Config Windows**: Transitioned configuration views to modeless UI widgets to allow concurrently deck browsing.
- **Smart Stability Patches**: Disabled aggressive LaTeX fixes by default and added dynamic offline status animations.

### May 9, 2026
- **Robust JSON Parsing Layer**: Vendored the `json_repair` engine and added hallucination filters to sanitize AI output strings.
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
