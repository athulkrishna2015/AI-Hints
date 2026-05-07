# AI-Hints Anki Add-on

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/D1D01W6NQT)

AI-Hints is a powerful Anki add-on that uses Artificial Intelligence to generate helpful hints or multiple-choice options for your flashcards during review. It helps simulate real exam conditions by including the correct answer alongside plausible distractors even for open-ended cards.
Install from [anki web ](https://ankiweb.net/shared/info/2119980872)
github:[https://github.com/athulkrishna2015/AI-Hints](https://github.com/athulkrishna2015/AI-Hints)
## Features

- **Multi-Provider Support**: Supports OpenAI, Anthropic, Gemini, Groq, DeepSeek, NVIDIA, Mistral, Grok, OpenRouter, **Together AI**, **Hugging Face**, **SambaNova**, **Cerebras**, and any OpenAI-compatible local API (like Ollama or LM Studio).
- **Automatic Fallback**: If your primary AI provider fails (e.g., rate limits or API downtime), the add-on automatically attempts to generate hints using your next configured provider.
- **Model Fallbacks**: If a configured model is unavailable or returns unusable output, the add-on can try fallback models for the same provider before moving on.
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
- **MathJax-Aware Rendering**: AI-Hints preserves and repairs common LaTeX/MathJax output, including escaped JSON backslashes, inline/display delimiters, bare variables such as `lambda_L`, and malformed nested delimiters returned by models.
- **Field Customization**: Specify exactly which fields to send to the AI for each note type. Optimized for Cloze cards by default.
- **Persistent Storage**: Generated hints are saved directly in your card's fields (e.g., "Extras" or "Back"), so they work on AnkiMobile and AnkiDroid too.
- **Manual Control**: Generate, show, or regenerate hints with buttons on the card, the review bar, or both.

## Release Notes

### 1.0.0

- Improved MathJax handling for AI-generated hints and options.
- Repairs common malformed model output such as missing LaTeX command slashes, mixed delimiters like `( ... \)`, and nested delimiters inside larger formulas.
- Preserves valid `\( ... \)`, `\[ ... \]`, and `<anki-mathjax>` content without wrapping entire prose sentences as math.
- Keeps visible HTML storage escaped while still allowing Anki MathJax tags.

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
- **Mistral**: [console.mistral.ai](https://console.mistral.ai/api-keys/)
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

## License

MIT
