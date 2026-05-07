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

Go to **Tools -> Add-ons -> AI-Hints -> Config** to set up your providers.

### Configuration Options

- `ai_provider`: The AI service to use (e.g., `openai`, `anthropic`, `gemini`, `deepseek`, `groq`, `local`, etc.).
- `storage_mode`: `"html"` (visible block) or `"json"` (hidden data block).
- `options_count`: Number of distractors to generate.
- `api_keys`: Your API keys for the respective providers.
- `local_endpoint`: URL and model name for local LLMs like Ollama.
- `note_type_fields`: A map of note type names to lists of fields that should be sent to the AI.
- `system_prompt`: The base instructions for the AI.

### Example Config:
```json
{
    "ai_provider": "openai",
    "storage_mode": "html",
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
