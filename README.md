# AI-Hints Anki Add-on

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/D1D01W6NQT)

AI-Hints is a powerful Anki add-on that uses Artificial Intelligence to generate helpful hints or multiple-choice distractors for your flashcards during review. It helps simulate real exam conditions by providing plausible options even for open-ended cards.

## Features

- **Multi-Provider Support**: Supports OpenAI, Anthropic, Gemini, Groq, DeepSeek, NVIDIA, Mistral, Grok, OpenRouter, and any OpenAI-compatible local API (like Ollama or LM Studio).
- **Custom AI Support**: Define your own custom endpoints and headers.
- **Universal Compatibility**: Works with Basic, Cloze, Image Occlusion, and custom note types.
- **Smart Shuffling**: Options are shuffled every time you review the card to prevent pattern memorization.
- **Storage Modes**: Choose between **visible HTML** (visible on all devices) or **invisible JSON** (cleaner look, requires add-on to render).
- **Configurable Options**: Set exactly how many distractors the AI should generate (default is 4).
- **Field Customization**: Specify exactly which fields to send to the AI for each note type. Optimized for Cloze cards by default.
- **Persistent Storage**: Generated hints are saved directly in your card's fields (e.g., "Extras" or "Back"), so they work on AnkiMobile and AnkiDroid too.
- **Manual Control**: Generate, show, or regenerate hints with embedded buttons on the card.

## Configuration

Go to **Tools -> Add-ons -> AI-Hints -> Config** to open the graphical configuration window.

### Configuration Options

- **General Tab**: Select your `ai_provider`, configure the number of distractors (`options_count`), toggle the visibility of the buttons, and choose the `storage_mode` (`"json"` for a hidden data block or `"html"` for a visible block).
- **AI Providers Tab**: Enter your `api_keys` for supported providers, configure a local LLM endpoint (like Ollama), or use the **Custom Providers** section to add, edit, or remove your own API endpoints and custom headers!
- **Advanced Tab**: 
  - `system_prompt`: The base instructions for the AI.
  - `Note Type Fields`: A graphical dropdown selector that allows you to specify exactly which fields should be sent to the AI for each of your specific note types.

## Get Your API Keys

To use this add-on, you need an API key from one of the supported providers:

- **OpenAI**: [platform.openai.com](https://platform.openai.com/api-keys)
- **Anthropic (Claude)**: [console.anthropic.com](https://console.anthropic.com/)
- **Google Gemini**: [aistudio.google.com](https://aistudio.google.com/app/apikey)
- **Groq**: [console.groq.com](https://console.groq.com/keys)
- **DeepSeek**: [platform.deepseek.com](https://platform.deepseek.com/api_keys)
- **OpenRouter**: [openrouter.ai](https://openrouter.ai/keys)
- **Mistral**: [console.mistral.ai](https://console.mistral.ai/api-keys/)
- **Grok (xAI)**: [console.x.ai](https://console.x.ai/)
- **NVIDIA**: [build.nvidia.com](https://build.nvidia.com/explore/discover)
- **Ollama (Local AI)**: [ollama.com](https://ollama.com/) (No API key required for local use)

### Example Config (Advanced Users):
You can also use the **Raw JSON Editor** in the Advanced tab if you prefer editing JSON directly:
```json
{
    "ai_provider": "openai",
    "storage_mode": "json",
    "options_count": 4,
    "api_keys": {
        "openai": "sk-...",
        "groq": "gsk_..."
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
