# Installation & API Keys

## Requirements

- **Anki** 25.x or newer (Qt 6, PyQt 6, Python 3.10+).
- An account/key for at least one supported AI provider.

## Install from AnkiWeb

The easiest way to install is through AnkiWeb:

1. Open Anki.
2. Go to **Tools → Add-ons → Get Add-ons…**.
3. Paste the code `2119980872` and press **OK**.
4. Restart Anki.

Or install directly: <https://ankiweb.net/shared/info/2119980872>

## Install from GitHub (development)

For developers, see [DEVELOPMENT.md](../DEVELOPMENT.md).

## Get Your API Keys

AI-Hints is provider-agnostic. Get a key from one (or more) of the supported providers:

| Provider | Key page |
|----------|----------|
| **Google Gemini** | https://aistudio.google.com/app/apikey |
| **OpenAI** | https://platform.openai.com/api-keys |
| **Anthropic** | https://console.anthropic.com/ |
| **Groq** | https://console.groq.com/keys |
| **SambaNova** | https://cloud.sambanova.ai/apis |
| **Hugging Face** | https://huggingface.co/settings/tokens |
| **OpenRouter** | https://openrouter.ai/keys |
| **DeepSeek**, **Grok (xAI)**, **NVIDIA**, **Mistral**, **Cerebras** | visit each provider's developer portal |

## Where to Enter Your Keys

1. Open Anki.
2. Go to **Tools → Add-ons → AI-Hints → Config**.
3. Open the **AI Providers** tab.
4. Select a provider, paste your API key into its field, pick a model, and click **Test** to verify connectivity.

### Multiple API Keys per Provider

Each provider key field supports **multiple keys** for automatic rotation and fallback:

- `name:key` — a named key
- `key (name)` — a named key
- Separate multiple keys with commas, semicolons, or newlines.

You can also click the **🔑** button next to a provider to open the **Manage Multiple API Keys** dialog, where keys can be labeled, individually enabled/disabled, and rotated.

### Custom Providers (local / OpenAI-compatible)

You can add any OpenAI-compatible endpoint (Ollama, LM Studio, vLLM, AIHubMix, etc.):

1. In the **AI Providers** tab, click **Add** under Custom Providers.
2. Fill in a **Provider Name**, **Endpoint URL**, and optionally an **API Key**.
3. Click **Fetch** to load models, then select one.

Local endpoints without authentication can leave the API key blank.

## Verify Your Setup

After entering a key:

1. Click **Test** on the provider row. A ✅ status means the connection works.
2. Optionally click **Test All** to check every configured provider.
3. Review a card and click the **Generate** button (or use a shortcut) to confirm hints and options appear.

If you run into issues, see [Troubleshooting](troubleshooting.md).
