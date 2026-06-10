import json
import time
import os
import re
import html
import urllib.request
import urllib.error
import urllib.parse
import socket
import threading
from typing import List, Dict, Any, Tuple
from .logger import logger, state

try:
    from .json_repair import loads as repair_loads
except ImportError:
    repair_loads = json.loads

ADDON_PATH = os.path.dirname(__file__)
BLACKLIST_FILE = os.path.join(ADDON_PATH, "blacklist.json")
REQUEST_TIMEOUT_SECONDS = 10
USER_AGENT = "Anki-AI-Hints/1.0"
GEMINI_PROVIDER_EXHAUSTED_STATUSES = {429}
MODEL_COOLDOWN_SECONDS = 3600  # 1 hour
FAILED_MODELS_CACHE: Dict[Tuple[str, str], float] = {}  # (provider, model) -> expiry_timestamp
FAILED_KEYS_CACHE: Dict[Tuple[str, str], float] = {}    # (provider, api_key) -> expiry_timestamp
RATE_LIMIT_STREAK: Dict[Tuple[str, str], int] = {}    # (provider, model) -> consecutive_hits
_BLACKLIST_LOADED = False

# Global network state for background monitoring
_NETWORK_STATE = {"online": True, "last_check": 0}

def _check_network_online() -> bool:
    """Internal helper to perform a quick connectivity check."""
    try:
        # Check Cloudflare DNS (1.1.1.1) on port 53 (DNS)
        socket.create_connection(("1.1.1.1", 53), timeout=1.5)
        _NETWORK_STATE["online"] = True
    except OSError:
        _NETWORK_STATE["online"] = False
    _NETWORK_STATE["last_check"] = time.time()
    return _NETWORK_STATE["online"]

def _start_network_monitor():
    """Starts a background thread to periodically update network status."""
    def monitor():
        while True:
            _check_network_online()
            time.sleep(30)
    t = threading.Thread(target=monitor, daemon=True)
    t.name = "AI-Hints-NetworkMonitor"
    t.start()

# Initialize monitor
_start_network_monitor()

PROVIDER_ORDER = [
    "anthropic",
    "openai",
    "deepseek",
    "grok",
    "gemini",
    "openrouter",
    "huggingface",
    "together",
    "groq",
    "sambanova",
    "nvidia",
    "mistral",
    "cerebras",
    "antigravity",
    "local",
]

DEFAULT_MODELS = {
    "openai":     "gpt-4o",
    "anthropic":  "claude-3-7-sonnet-latest",
    "gemini":     "gemini-2.5-flash",
    "groq":       "llama-3.3-70b-versatile",
    "deepseek":   "deepseek-reasoner",
    "grok":       "grok-2-1212",
    "mistral":    "mistral-large-latest",
    "openrouter": "deepseek/deepseek-chat",
    "nvidia":     "meta/llama-3.3-70b-instruct",
    "huggingface": "deepseek-ai/DeepSeek-V3",
    "together":   "meta-llama/Llama-3.3-70B-Instruct-Turbo",
    "sambanova":  "Meta-Llama-3.3-70B-Instruct",
    "cerebras":   "llama3.1-8b",
    "antigravity":"gemini-3.1-flash-lite",
    "local":      "llama3.3",
}

# Popular model suggestions for the UI dropdowns
MODEL_SUGGESTIONS = {
    "openai": [
        "gpt-4o-mini",
        "gpt-4o",
        "o1-mini",
        "o3-mini",
    ],
    "anthropic": [
        "claude-3-5-haiku-latest",
        "claude-3-5-sonnet-latest",
        "claude-3-7-sonnet-latest",
    ],
    "gemini": [
        "gemini-3.1-flash-lite",
        "gemini-flash-lite-latest",
        "gemini-3.1-flash-lite-preview",
        "gemini-2.5-flash-lite",
        "gemma-4-31b-it",
        "gemini-3.1-pro-preview",
        "gemini-3-pro-preview",
        "gemini-2.5-pro",
        "gemini-pro-latest",
        "gemini-3-flash-preview",
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-flash-latest",
        "gemini-2.0-flash-lite",
    ],
    "groq": [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "llama-3.1-70b-versatile",
        "mixtral-8x7b-32768",
        "deepseek-r1-distill-llama-70b",
    ],
    "openrouter": [
        "google/gemini-2.0-flash-001",
        "google/gemini-2.0-flash-lite-001",
        "openai/gpt-4o-mini",
        "anthropic/claude-3.5-haiku",
        "deepseek/deepseek-chat",
        "meta-llama/llama-3.3-70b-instruct",
    ],
    "deepseek": [
        "deepseek-chat",
        "deepseek-reasoner",
    ],
    "mistral": [
        "mistral-small-latest",
        "mistral-medium-latest",
        "mistral-large-latest",
        "pixtral-12b-2409",
    ],
    "together": [
        "meta-llama/Llama-3.3-70B-Instruct-Turbo",
        "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo",
        "deepseek-ai/DeepSeek-V3",
        "mistralai/Mixtral-8x7B-Instruct-v0.1",
    ],
    "sambanova": [
        "Meta-Llama-3.3-70B-Instruct",
    ],
    "cerebras": [
        "llama-3.3-70b",
        "llama3.1-8b",
    ],
    "huggingface": [
        "deepseek-ai/DeepSeek-V3",
        "meta-llama/Llama-3.3-70B-Instruct",
        "Qwen/Qwen2.5-72B-Instruct",
    ],
    "antigravity": [
        "gemini-3.1-flash-lite",
        "gemini-3-flash",
        "gemini-2.5-flash",
        "gemini-2-flash",
        "gemini-2.5-pro",
    ],
}

LEGACY_MODEL_REPLACEMENTS = {
    ("anthropic", "claude-3-haiku-20240307"): "claude-3-5-haiku-latest",
    ("gemini", "gemini-1.5-flash"): "gemini-2.0-flash",
    ("gemini", "models/gemini-1.5-flash"): "gemini-2.0-flash",
    ("gemini", "models/gemini-2.0-flash-exp"): "gemini-2.0-flash",
    ("gemini", "gemini-1.5-pro"): "gemini-pro-latest",
    ("gemini", "gemini-2.0-pro-exp-02-05"): "gemini-2.5-pro",
    ("gemini", "gemini-3.1-flash-lite-preview"): "gemini-3.1-flash-lite",
    ("groq", "llama3-8b-8192"): "llama-3.1-8b-instant",
    ("groq", "llama3-70b-8192"): "llama-3.3-70b-versatile",
    ("grok", "grok-1"): "grok-2-1212",
    ("huggingface", "meta-llama/Meta-Llama-3-8B-Instruct"): "meta-llama/Llama-3.1-8B-Instruct",
    ("nvidia", "meta/llama3-8b-instruct"): "meta/llama-3.1-8b-instruct",
    ("openrouter", "meta-llama/llama-3-8b-instruct"): "meta-llama/llama-3.1-8b-instruct",
    ("openrouter", "google/gemini-3.1-flash"): "google/gemini-2.0-flash-001",
    ("openrouter", "google/gemini-2.0-flash-exp:free"): "google/gemini-2.0-flash-001",
    ("together", "mistralai/Mixtral-8x7B-Instruct-v0.1"): "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo",
    ("sambanova", "Meta-Llama-3.1-8B-Instruct"): "Meta-Llama-3.3-70B-Instruct",
    ("cerebras", "llama3.1-8b"): "llama-3.1-8b",
    ("cerebras", "llama3.1-70b"): "llama-3.3-70b",
}

MODEL_FALLBACKS = {
    "anthropic": [
        "claude-3-7-sonnet-latest",
        "claude-3-5-sonnet-latest",
        "claude-3-5-haiku-latest",
    ],
    "gemini": [
        "gemini-3.1-flash-lite",
        "gemini-flash-lite-latest",
        "gemini-3.1-flash-lite-preview",
        "gemini-2.5-flash-lite",
        "gemini-3.1-pro-preview",
        "gemini-3-pro-preview",
        "gemini-2.5-pro",
        "gemini-pro-latest",
        "gemini-3-flash-preview",
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-flash-latest",
        "gemini-2.0-flash-lite",
    ],
    "groq": [
        "llama-3.3-70b-versatile",
        "mixtral-8x7b-32768",
        "llama-3.1-8b-instant",
    ],
    "grok": [
        "grok-2-1212",
    ],
    "huggingface": [
        "deepseek-ai/DeepSeek-V3",
        "meta-llama/Llama-3.3-70B-Instruct",
        "Qwen/Qwen2.5-72B-Instruct",
    ],
    "openai": [
        "gpt-4o",
        "o1-mini",
        "gpt-4o-mini",
    ],
    "nvidia": [
        "meta/llama-3.3-70b-instruct",
        "meta/llama-3.1-8b-instruct",
    ],
    "openrouter": [
        "google/gemini-2.0-flash-001",
        "google/gemini-2.0-flash-lite-001",
        "anthropic/claude-3.5-sonnet",
        "openai/gpt-4o",
        "deepseek/deepseek-chat",
        "meta-llama/llama-3.3-70b-instruct",
        "openrouter/auto",
    ],
    "together": [
        "meta-llama/Llama-3.3-70B-Instruct-Turbo",
        "deepseek-ai/DeepSeek-V3",
        "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo",
    ],
    "sambanova": [
        "Meta-Llama-3.3-70B-Instruct",
    ],
    "cerebras": [
        "llama-3.3-70b",
        "llama-3.1-8b",
    ],
    "antigravity": [
        "gemini-3.1-flash-lite",
        "gemini-3-flash",
        "gemini-2.5-flash",
        "gemini-2-flash",
        "gemini-2.5-pro",
    ],
}




class AIClient:
    def __init__(self, config: Dict[str, Any]):
        self.config = config or {}
        self._key_names: Dict[Tuple[str, str], str] = {}

    def generate_options(self, front: str, back: str, override_provider: str = None, only_this_provider: bool = False) -> Dict[str, List[str]]:
        primary_provider = override_provider or self.config.get("ai_provider", "openai")
        system_prompt = (self.config.get("system_prompt", "") or "").strip()
        count = self._options_count()
        
        # Add strict formatting every time; user-provided prompts often omit the exact count.
        system_prompt = (
            f"{system_prompt}\n\n" if system_prompt else ""
        ) + (
            "CRITICAL:\n"
            f"- Generate exactly {count} total options (1 correct, {count-1} distractors) and 2-3 conceptual hints.\n"
            "- Return ONLY strictly valid raw JSON. No markdown, no preambles.\n"
            "- If using 'distractors' key, provide only incorrect options. If 'options', include the correct answer.\n"
            "- Ensure all options match the correct answer's format, length, and style perfectly.\n"
            "- For multiple clozes with same ID, use comma-separated values (e.g., 'val1, val2').\n"
        )
        prompt = f"Front: {front}\nBack / correct answer: {back}" if back else f"Content: {front}"

        # Check if we should use the advanced global priority list
        global_priority = self.config.get("global_model_priority", [])
        use_global = self.config.get("use_global_model_priority", False)
        from .logger import log_context
        is_test = getattr(log_context, "source", None) == "model_test"
        
        if use_global and global_priority and not override_provider and not is_test:
            disabled_providers = self.config.get("disabled_providers") or []
            disabled_fallback_models = self.config.get("disabled_fallback_models") or {}
            
            last_exception = None
            for provider, model in global_priority:
                if state.GLOBAL_STOP:
                    logger.info(f"AI-Hints: Generation aborted via Emergency Stop signal (global loop).")
                    return {"hints": [], "options": []}
                
                # Skip if provider is disabled
                if provider in disabled_providers:
                    continue
                # Skip if model is disabled
                if model in disabled_fallback_models.get(provider, []):
                    continue
                # Skip if provider is not ready
                if not self._is_provider_ready(provider, primary=True):
                    continue
                # Skip if model is blacklisted on cooldown
                if self._is_model_failed(provider, model):
                    continue
                
                try:
                    logger.info(f"AI-Hints: Calling {provider} with model: {model} (via global priority)")
                    result = self._call_provider(provider, system_prompt, prompt, override_model=model)
                    if result.get("hints") or result.get("options") or result.get("distractors") or result.get("correct_answer"):
                        result = self._ensure_correct_answer_option(result, back)
                        logger.debug(f"AI-Hints: Successful generation using: {provider}/{model}")
                        return result
                except Exception as e:
                    last_exception = e
                    logger.error(f"Global fallback model {provider}/{model} failed: {e}")
                    continue
            
            if last_exception:
                raise last_exception
            return {"hints": [], "options": []}

        # Otherwise fallback to standard provider-based priority logic
        if only_this_provider:
            all_potential = [primary_provider] if self._is_provider_ready(primary_provider, primary=True) else []
        else:
            all_potential = self._candidate_providers(primary_provider)
        if not all_potential:
            logger.error("AI-Hints: No configured AI provider is ready.")
            return {"hints": [], "options": []}
        
        last_exception = None
        # Try providers in sequence
        for provider in all_potential:
            if state.GLOBAL_STOP:
                logger.info(f"AI-Hints: Generation aborted via Emergency Stop signal (provider loop).")
                return {"hints": [], "options": []}
            try:
                result = self._call_provider(provider, system_prompt, prompt)
                if result.get("hints") or result.get("options") or result.get("distractors") or result.get("correct_answer"):
                    result = self._ensure_correct_answer_option(result, back)
                    if provider != primary_provider:
                        logger.debug(f"AI-Hints: Fallback successful using provider: {provider}")
                    return result
            except Exception as e:
                last_exception = e
                logger.error(f"Provider {provider} failed: {e}")
                continue
                
        if last_exception:
            raise last_exception
            
        return {"hints": [], "options": []}

    def has_ready_provider(self, provider: str) -> bool:
        return self._is_provider_ready(provider, primary=True)

    def has_any_ready_provider(self) -> bool:
        primary = self.config.get("ai_provider", "openai")
        return bool(self._candidate_providers(primary))

    def _candidate_providers(self, primary_provider: str) -> List[str]:
        from .logger import log_context
        if getattr(log_context, "source", None) == "model_test":
            return [primary_provider]

        custom_provider_config = self.config.get("custom_providers") or {}
        if not isinstance(custom_provider_config, dict):
            custom_provider_config = {}
        custom_providers = list(custom_provider_config.keys())
        
        # Filter out disabled providers
        disabled = self.config.get("disabled_providers")
        if not isinstance(disabled, list):
            disabled = []

        # Use custom priority list if configured, otherwise use default order
        priority = self.config.get("provider_priority")
        if not isinstance(priority, list):
            priority = PROVIDER_ORDER + custom_providers
            
        priority = [p for p in priority if p not in disabled]
            
        candidates = []

        if primary_provider not in disabled and self._is_provider_ready(primary_provider, primary=True):
            candidates.append(primary_provider)
        else:
            logger.warning(
                f"AI-Hints: Primary provider '{primary_provider}' is not configured or is disabled; checking fallbacks."
            )

        for provider in priority:
            if provider == primary_provider or provider in candidates:
                continue
            if self._is_provider_ready(provider, primary=False):
                candidates.append(provider)
        return candidates

    def _is_provider_ready(self, provider: str, primary: bool = False) -> bool:
        if provider == "local":
            local_cfg = self.config.get("local_endpoint") or {}
            if not isinstance(local_cfg, dict):
                local_cfg = {}
            if primary:
                return True
            return bool(local_cfg.get("enabled", False))

        if provider == "antigravity":
            ag_cfg = self.config.get("antigravity_proxy") or {}
            if not isinstance(ag_cfg, dict):
                ag_cfg = {}
            if primary:
                return True
            return bool(ag_cfg.get("enabled", False))

        custom_providers = self.config.get("custom_providers") or {}
        if not isinstance(custom_providers, dict):
            custom_providers = {}
        if provider in custom_providers:
            custom_cfg = custom_providers[provider]
            if not isinstance(custom_cfg, dict):
                return False
            url = str(custom_cfg.get("url", "") or "").strip()
            model = str(custom_cfg.get("model", "") or "").strip()
            return bool(url and model)

        return bool(self._api_key_for(provider))

    def _call_provider(self, provider: str, system_prompt: str, prompt: str, override_model: str = "") -> Dict[str, List[str]]:
        custom_providers = self.config.get("custom_providers") or {}
        if not isinstance(custom_providers, dict):
            custom_providers = {}
        if provider == "anthropic":
            return self._call_anthropic(system_prompt, prompt, override_model=override_model)
        elif provider == "gemini":
            return self._call_gemini(system_prompt, prompt, override_model=override_model)
        elif provider in custom_providers:
            return self._call_custom_provider(provider, system_prompt, prompt, override_model=override_model)
        else:
            return self._call_openai_compatible(provider, system_prompt, prompt, override_model=override_model)

    def _call_custom_provider(self, provider_name: str, system_prompt: str, prompt: str, override_model: str = "") -> Dict[str, List[str]]:
        custom_providers = self.config.get("custom_providers") or {}
        if not isinstance(custom_providers, dict):
            custom_providers = {}
        custom_cfg = custom_providers.get(provider_name, {})
        if not isinstance(custom_cfg, dict):
            custom_cfg = {}
        url = str(custom_cfg.get("url", "") or "").strip()
        
        keys = self._api_keys_for_custom(provider_name, custom_cfg)
        if not keys:
            keys = [""]
            
        custom_headers = custom_cfg.get("headers", {})
        if not isinstance(custom_headers, dict):
            custom_headers = {}

        models = [override_model] if override_model else self._models_for_provider(provider_name, custom_cfg.get("model", ""), custom_cfg.get("model_fallbacks", []))

        now = time.time()
        available_keys = []
        for key in keys:
            if key:
                expiry = FAILED_KEYS_CACHE.get((provider_name, key))
                if expiry is None or now > expiry:
                    available_keys.append(key)
            else:
                available_keys.append(key)
                
        if not available_keys:
            available_keys = keys

        for idx, api_key in enumerate(available_keys):
            headers = self._json_headers(api_key)
            headers.update(custom_headers)

            key_failed = False
            for model in models:
                if state.GLOBAL_STOP:
                    break
                data = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ]
                }

                try:
                    self._log_model_attempt(provider_name, model, models)
                    result = self._post_json(url, data, headers)
                    content = self._extract_content(result)
                    parsed = self._parse_json_result(content)
                    if parsed.get("hints") or parsed.get("options") or parsed.get("distractors") or parsed.get("correct_answer"):
                        self._on_key_success(provider_name, api_key)
                        self._on_model_success(provider_name, model)
                        parsed["_provider"] = provider_name
                        parsed["_model"] = model
                        parsed["_generated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                        return parsed
                    logger.warning(f"AI-Hints: Custom provider {provider_name} model '{model}' returned no parseable hints/options.")
                except urllib.error.HTTPError as e:
                    body = self._read_http_error(e)
                    logger.error(f"AI-Hints Error (Custom Provider {provider_name}, model {model}): {e} - {body}")
                    from .logger import log_context
                    if getattr(log_context, "source", None) == "model_test":
                        if idx == len(available_keys) - 1:
                            raise Exception(f"{e} - {body}")
                        else:
                            self._mark_key_failed(provider_name, api_key)
                            key_failed = True
                            break
                    if e.code in [401, 403, 429]:
                        self._mark_key_failed(provider_name, api_key)
                        key_failed = True
                        break
                    if e.code in [404, 500, 503]:
                        delay = self._extract_retry_delay(provider_name, model, e, body)
                        self._mark_model_failed(provider_name, model, delay)
                        continue
                except Exception as e:
                    logger.error(f"AI-Hints Error (Custom Provider {provider_name}, model {model}): {e}")
                    self._mark_key_failed(provider_name, api_key)
                    key_failed = True
                    break
            
            if key_failed:
                continue

        return {"hints": [], "options": []}

    def _call_openai_compatible(self, provider: str, system_prompt: str, prompt: str, override_model: str = "") -> Dict[str, List[str]]:
        keys = self._available_api_keys(provider)
        if not keys and provider in ["local", "antigravity"]:
            keys = [""]
        elif not keys:
            return {"hints": [], "options": []}

        models = [override_model] if override_model else self._models_for_provider(provider)
        
        base_url = "https://api.openai.com/v1"
        if provider == "deepseek":
            base_url = "https://api.deepseek.com"
        elif provider == "groq":
            base_url = "https://api.groq.com/openai/v1"
        elif provider == "nvidia":
            base_url = "https://integrate.api.nvidia.com/v1"
        elif provider == "grok":
            base_url = "https://api.x.ai/v1"
        elif provider == "openrouter":
            base_url = "https://openrouter.ai/api/v1"
        elif provider == "local":
            local_cfg = self.config.get("local_endpoint") or {}
            if not isinstance(local_cfg, dict):
                local_cfg = {}
            base_url = local_cfg.get("base_url", "http://localhost:11434/v1")
            models = [override_model] if override_model else self._models_for_provider(provider, local_cfg.get("model", "") or DEFAULT_MODELS["local"])
        elif provider == "antigravity":
            ag_cfg = self.config.get("antigravity_proxy") or {}
            if not isinstance(ag_cfg, dict):
                ag_cfg = {}
            port = ag_cfg.get("port", 3000)
            base_url = f"http://localhost:{port}/v1"
            models = [override_model] if override_model else self._models_for_provider(provider, DEFAULT_MODELS["antigravity"])
        elif provider == "mistral":
            base_url = "https://api.mistral.ai/v1"
        elif provider == "huggingface":
            base_url = "https://router.huggingface.co/v1"
        elif provider == "together":
            base_url = "https://api.together.xyz/v1"
        elif provider == "sambanova":
            base_url = "https://api.sambanova.ai/v1"
        elif provider == "cerebras":
            base_url = "https://api.cerebras.ai/v1"
        
        url = f"{base_url}/chat/completions"

        for idx, api_key in enumerate(keys):
            if provider == "local":
                local_cfg = self.config.get("local_endpoint") or {}
                actual_key = str(local_cfg.get("api_key", "") or api_key).strip()
            elif provider == "antigravity":
                actual_key = "antigravity"
            else:
                actual_key = api_key

            headers = self._json_headers(actual_key)
            if provider == "openrouter":
                headers["HTTP-Referer"] = "https://github.com/athulkrishna2015/ai-hints"
                headers["X-Title"] = "Anki AI-Hints"

            # OpenRouter supports a 'models' array for automatic server-side fallbacks
            if provider == "openrouter" and len(models) > 1:
                data = {
                    "models": models[:3],
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    "response_format": {"type": "json_object"}
                }
                try:
                    logger.debug(f"Calling OpenRouter with models array: {models}")
                    result = self._post_json(url, data, headers)
                    content = self._extract_content(result)
                    parsed = self._parse_json_result(content)
                    if parsed.get("hints") or parsed.get("options") or parsed.get("distractors") or parsed.get("correct_answer"):
                        self._on_key_success(provider, api_key)
                        actual_model = result.get("model", "openrouter-auto")
                        parsed["_provider"] = "openrouter"
                        parsed["_model"] = actual_model
                        parsed["_generated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                        return parsed
                    logger.warning("AI-Hints: OpenRouter models array returned no parseable hints/options.")
                except urllib.error.HTTPError as e:
                    body = self._read_http_error(e)
                    logger.error(f"AI-Hints Error (OpenRouter models array): {e} - {body}")
                    from .logger import log_context
                    if getattr(log_context, "source", None) == "model_test":
                        if idx == len(keys) - 1:
                            raise Exception(f"{e} - {body}")
                        else:
                            self._mark_key_failed(provider, api_key)
                            continue
                    if e.code in [401, 403, 429]:
                        self._mark_key_failed(provider, api_key)
                        continue
                except Exception as e:
                    logger.error(f"AI-Hints Error (OpenRouter models array): {e}")
                    self._mark_key_failed(provider, api_key)
                    continue

            key_failed = False
            for model in models:
                if state.GLOBAL_STOP:
                    break
                data = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                }
                if provider in ["openai", "groq", "deepseek", "mistral", "openrouter", "together", "sambanova", "cerebras", "nvidia"]:
                    data["response_format"] = {"type": "json_object"}

                try:
                    self._log_model_attempt(provider, model, models)
                    result = self._post_json(url, data, headers)
                    content = self._extract_content(result)
                    parsed = self._parse_json_result(content)
                    if parsed.get("hints") or parsed.get("options") or parsed.get("distractors") or parsed.get("correct_answer"):
                        self._on_key_success(provider, api_key)
                        self._on_model_success(provider, model)
                        parsed["_provider"] = provider
                        parsed["_model"] = model
                        parsed["_generated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                        return parsed
                    logger.warning(f"AI-Hints: {provider} model '{model}' returned no parseable hints/options.")
                except urllib.error.HTTPError as e:
                    body = self._read_http_error(e)
                    logger.error(f"AI-Hints Error ({provider}, model {model}): {e} - {body}")
                    from .logger import log_context
                    if getattr(log_context, "source", None) == "model_test":
                        if idx == len(keys) - 1:
                            raise Exception(f"{e} - {body}")
                        else:
                            self._mark_key_failed(provider, api_key)
                            key_failed = True
                            break
                    if e.code in [401, 403, 429]:
                        self._mark_key_failed(provider, api_key)
                        key_failed = True
                        break
                    if e.code in [404, 500, 503]:
                        delay = self._extract_retry_delay(provider, model, e, body)
                        self._mark_model_failed(provider, model, delay)
                        continue
                except Exception as e:
                    logger.error(f"AI-Hints Error ({provider}, model {model}): {e}")
                    self._mark_key_failed(provider, api_key)
                    key_failed = True
                    break
            
            if key_failed:
                continue

        return {"hints": [], "options": []}

    def _call_anthropic(self, system_prompt: str, prompt: str, override_model: str = "") -> Dict[str, List[str]]:
        keys = self._available_api_keys("anthropic")
        if not keys:
            return {"hints": [], "options": []}
            
        models = [override_model] if override_model else self._models_for_provider("anthropic")
        url = "https://api.anthropic.com/v1/messages"
        
        for idx, api_key in enumerate(keys):
            headers = self._json_headers()
            headers.update({
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01"
            })

            key_failed = False
            for model in models:
                if state.GLOBAL_STOP:
                    break
                data = {
                    "model": model,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 1024
                }

                try:
                    self._log_model_attempt("anthropic", model, models)
                    result = self._post_json(url, data, headers)
                    content = self._extract_content(result)
                    parsed = self._parse_json_result(content)
                    if parsed.get("hints") or parsed.get("options") or parsed.get("distractors") or parsed.get("correct_answer"):
                        self._on_key_success("anthropic", api_key)
                        self._on_model_success("anthropic", model)
                        parsed["_provider"] = "anthropic"
                        parsed["_model"] = model
                        parsed["_generated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                        return parsed
                    logger.warning(f"AI-Hints: Anthropic model '{model}' returned no parseable hints/options.")
                except urllib.error.HTTPError as e:
                    body = self._read_http_error(e)
                    logger.error(f"AI-Hints Error (Anthropic, model {model}): {e} - {body}")
                    from .logger import log_context
                    if getattr(log_context, "source", None) == "model_test":
                        if idx == len(keys) - 1:
                            raise Exception(f"{e} - {body}")
                        else:
                            self._mark_key_failed("anthropic", api_key)
                            key_failed = True
                            break
                    if e.code in [401, 403, 429]:
                        self._mark_key_failed("anthropic", api_key)
                        key_failed = True
                        break
                    if e.code in [404, 500, 503]:
                        delay = self._extract_retry_delay("anthropic", model, e, body)
                        self._mark_model_failed("anthropic", model, delay)
                        continue
                except Exception as e:
                    logger.error(f"AI-Hints Error (Anthropic, model {model}): {e}")
                    self._mark_key_failed("anthropic", api_key)
                    key_failed = True
                    break
            
            if key_failed:
                continue

        return {"hints": [], "options": []}

    def _call_gemini(self, system_prompt: str, prompt: str, override_model: str = "") -> Dict[str, List[str]]:
        keys = self._available_api_keys("gemini")
        if not keys:
            return {"hints": [], "options": []}
            
        models = [override_model] if override_model else self._models_for_provider("gemini")

        for idx, api_key in enumerate(keys):
            headers = self._json_headers()
            headers["x-goog-api-key"] = api_key

            key_failed = False
            for model in models:
                if state.GLOBAL_STOP:
                    break
                model_path = urllib.parse.quote(model, safe="")
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_path}:generateContent"
                logger.debug(f"Calling Gemini with model: {model}")

                data = {
                    "system_instruction": {"parts": [{"text": system_prompt}]},
                    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "responseMimeType": "application/json"
                    },
                }

                lower_model = model.lower()
                supports_thinking = (
                    "gemini-3" in lower_model or 
                    "gemini-2.5" in lower_model or 
                    "gemini-flash-latest" in lower_model or 
                    "gemini-pro-latest" in lower_model or
                    "gemini-flash-lite-latest" in lower_model
                )
                
                if supports_thinking:
                    data["generationConfig"]["thinkingConfig"] = {
                        "includeThoughts": True,
                        "thinkingBudget": 1024
                    }

                try:
                    self._log_model_attempt("gemini", model, models)
                    result = self._post_json(url, data, headers)
                    content = self._extract_content(result)
                    parsed = self._parse_json_result(content)
                    if parsed.get("hints") or parsed.get("options") or parsed.get("distractors") or parsed.get("correct_answer"):
                        self._on_key_success("gemini", api_key)
                        self._on_model_success("gemini", model)
                        parsed["_provider"] = "gemini"
                        parsed["_model"] = model
                        parsed["_generated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                        return parsed
                    logger.warning(f"AI-Hints: Gemini model '{model}' returned no parseable hints/options.")
                except urllib.error.HTTPError as e:
                    body = self._read_http_error(e)
                    logger.error(f"AI-Hints Error (Gemini, model {model}): {e} - {body}")
                    from .logger import log_context
                    if getattr(log_context, "source", None) == "model_test":
                        if idx == len(keys) - 1:
                            raise Exception(f"{e} - {body}")
                        else:
                            self._mark_key_failed("gemini", api_key)
                            key_failed = True
                            break
                    if e.code in [401, 403, 429] or (e.code == 400 and ("API_KEY_INVALID" in body or "API key not valid" in body)):
                        self._mark_key_failed("gemini", api_key)
                        key_failed = True
                        break
                    if e.code in [404, 500, 503]:
                        delay = self._extract_retry_delay("gemini", model, e, body)
                        self._mark_model_failed("gemini", model, delay)
                        continue
                except Exception as e:
                    logger.error(f"AI-Hints Error (Gemini, model {model}): {e}")
                    self._mark_key_failed("gemini", api_key)
                    key_failed = True
                    break
            
            if key_failed:
                continue

        return {"hints": [], "options": []}

    def submit_gemini_batch(self, batch_requests: List[Dict]) -> Dict:
        """
        Submits a list of requests to the Gemini Batch API (Inline).
        batch_requests: list of dicts with keys: 'key', 'system_prompt', 'user_prompt'
        Returns the batch definition response (containing 'name') or raises Exception.
        """
        keys = self._available_api_keys("gemini")
        if not keys:
            raise ValueError("No available Gemini API keys.")
            
        models = self._models_for_provider("gemini")
        if not models:
            raise ValueError("No Gemini models configured.")
        
        model = models[0] # Use best available model
        model_path = urllib.parse.quote(model, safe="")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_path}:batchGenerateContent"
        
        request_items = []
        for item in batch_requests:
            req_key = item["key"]
            sys_p = item["system_prompt"]
            u_p = item["user_prompt"]
            
            inner_req = {
                "contents": [{"role": "user", "parts": [{"text": u_p}]}],
                "generationConfig": {
                    "responseMimeType": "application/json"
                }
            }
            if sys_p:
                inner_req["system_instruction"] = {"parts": [{"text": sys_p}]}
            
            lower_model = model.lower()
            supports_thinking = (
                "gemini-3" in lower_model or 
                "gemini-2.5" in lower_model or 
                "gemini-flash-latest" in lower_model or 
                "gemini-pro-latest" in lower_model or
                "gemini-flash-lite-latest" in lower_model
            )

            if supports_thinking:
                inner_req["generationConfig"]["thinkingConfig"] = {
                    "includeThoughts": True,
                    "thinkingBudget": 1024
                }
            
            request_items.append({
                "request": inner_req,
                "metadata": {"key": req_key}
            })
            
        payload = {
            "batch": {
                "display_name": f"ai-hints-mass-gen-{int(time.time())}",
                "input_config": {
                    "requests": {
                        "requests": request_items
                    }
                }
            }
        }
        
        logger.info(f"Submitting Gemini Batch for {len(request_items)} items to model: {model}")
        last_err = None
        for api_key in keys:
            headers = self._json_headers()
            headers["x-goog-api-key"] = api_key
            try:
                response = self._post_json(url, payload, headers)
                self._on_key_success("gemini", api_key)
                return response
            except urllib.error.HTTPError as e:
                err_body = e.read().decode("utf-8", errors="ignore")
                if "FAILED_PRECONDITION" in err_body:
                     raise Exception("🔒 Access Denied: Your Gemini API key appears to be on the FREE TIER.\n\nNative Batch Generation is a Paid-Only feature. Please link a billing method in Google AI Studio to enable it, OR switch to the 'Sequential Local Queue' mode in your Batch tab for free support.")
                if e.code in [401, 403, 429] or (e.code == 400 and ("API_KEY_INVALID" in err_body or "API key not valid" in err_body)):
                    self._mark_key_failed("gemini", api_key)
                    last_err = Exception(f"Google API Error ({e.code}) with key {self._key_identifier('gemini', api_key)}: {err_body}")
                    continue
                raise Exception(f"Google API Error ({e.code}): {err_body}")
            except Exception as e:
                self._mark_key_failed("gemini", api_key)
                last_err = e
                continue
        if last_err:
            raise last_err
        raise ValueError("Failed to submit batch request with any available Gemini API key.")

    def get_gemini_batch_status(self, job_name: str) -> Dict:
        """
        Retrieve current status and potentially results for a running batch job.
        job_name should be in format 'batches/XXXXXXXX'
        """
        keys = self._available_api_keys("gemini")
        if not keys:
            raise ValueError("No available Gemini API keys.")
            
        job_name = job_name.lstrip("/")
        url = f"https://generativelanguage.googleapis.com/v1beta/{job_name}"
        
        last_err = None
        for api_key in keys:
            headers = self._json_headers()
            headers["x-goog-api-key"] = api_key
            try:
                req = urllib.request.Request(url, headers=headers, method="GET")
                with urllib.request.urlopen(req, timeout=30) as response:
                    raw = response.read().decode("utf-8")
                    self._on_key_success("gemini", api_key)
                    return json.loads(raw)
            except urllib.error.HTTPError as e:
                err_body = self._read_http_error(e)
                if e.code in [401, 403, 429] or (e.code == 400 and ("API_KEY_INVALID" in err_body or "API key not valid" in err_body)):
                    self._mark_key_failed("gemini", api_key)
                    last_err = Exception(f"Google API Error ({e.code}) with key {self._key_identifier('gemini', api_key)}: {err_body}")
                    continue
                raise
            except Exception as e:
                self._mark_key_failed("gemini", api_key)
                last_err = e
                continue
        if last_err:
            raise last_err
        raise ValueError("Failed to check batch status with any available Gemini API key.")

    def _parse_json_result(self, content: str) -> Dict[str, List[str]]:

        content = (content or "").strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        try:
            # Use json_repair for robust parsing of potentially malformed AI output
            parsed = repair_loads(content)
        except Exception:
            # Fallback: attempt to find and parse the first JSON object
            start = content.find("{")
            end = content.rfind("}")
            if start == -1 or end == -1 or end <= start:
                logger.warning("AI-Hints: Provider response did not contain JSON.")
                return {"hints": [], "options": []}
            try:
                parsed = repair_loads(content[start:end + 1])
            except Exception:
                logger.warning("AI-Hints: Provider response contained invalid JSON.")
                return {"hints": [], "options": []}

        if not isinstance(parsed, dict):
            return {"hints": [], "options": []}

        result = {
            "hints": self._normalize_string_list(parsed.get("hints", [])),
            "options": self._normalize_string_list(parsed.get("options", [])),
        }
        if "correct_answer" in parsed:
            result["correct_answer"] = parsed["correct_answer"]
        if "distractors" in parsed:
            result["distractors"] = self._normalize_string_list(parsed["distractors"])
        return result
    def _ensure_correct_answer_option(self, result: Dict[str, List[str]], answer: str) -> Dict[str, List[str]]:
        count = self._options_count()
        options = self._normalize_string_list(result.get("options", []))
        
        # If the LLM returned options, we assume the first one is the correct answer 
        # (as requested by the user's system prompt) OR we extract it from result.
        correct_answer_from_llm = ""
        if result.get("correct_answer"):
            correct_answer_from_llm = str(result["correct_answer"]).strip()
        elif options:
            correct_answer_from_llm = options[0]

        answer_text = self._clean_answer_for_option(answer)
        
        # If we have a reasonable LLM correct answer, use it over the raw Anki back field
        # to avoid dumping huge explanations into the options.
        if correct_answer_from_llm:
            chosen_answer = correct_answer_from_llm
        else:
            chosen_answer = answer_text

        if not chosen_answer:
            result["options"] = options[:count]
            return result

        answer_key = self._option_key(chosen_answer)
        deduped = []
        has_answer = False
        seen = set()
        for option in options:
            key = self._option_key(option)
            if not key or key in seen:
                continue
            if key == answer_key:
                has_answer = True
            seen.add(key)
            deduped.append(option)

        if not has_answer:
            if len(deduped) >= count:
                deduped = deduped[:max(count - 1, 0)]
            deduped.append(chosen_answer)

        result["options"] = deduped[:count]
        result["correct_answer"] = chosen_answer
        return result

    def _clean_answer_for_option(self, answer: str) -> str:
        if not answer:
            return ""
        text = str(answer)
        text = re.sub(r"<(script|style).*?>.*?</\1>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<.*?>", " ", text)
        text = html.unescape(text)
        text = " ".join(text.replace("\n", " ").split())
        return text.strip()

    def _option_key(self, text: str) -> str:
        """Normalized key for deduplicating options, ignoring math delimiters and whitespace."""
        text = str(text).strip().casefold()
        # Normalize math delimiters for comparison
        text = text.replace("\\(", "$").replace("\\)", "$")
        text = text.replace("\\[", "$$").replace("\\]", "$$")
        # Remove common delimiters for comparison
        text = text.replace("$", "").replace(" ", "")
        return text

    def _options_count(self) -> int:
        try:
            count = int(self.config.get("options_count", 4))
        except (TypeError, ValueError):
            count = 4
        return max(1, min(count, 10))

    def _api_keys(self) -> Dict[str, Any]:
        api_keys = self.config.get("api_keys") or {}
        return api_keys if isinstance(api_keys, dict) else {}

    def _api_key_for(self, provider: str) -> str:
        keys = self._available_api_keys(provider)
        return keys[0] if keys else ""

    def _parse_all_keys(self, provider: str, val: str) -> List[Dict[str, Any]]:
        val = str(val or "").strip()
        if not val:
            return []
        
        raw_entries = [e.strip() for e in re.split(r'[,\;\n\r]+', val) if e.strip()]
        
        results = []
        for entry in raw_entries:
            enabled = True
            entry_lower = entry.lower()
            if entry_lower.startswith("disabled:"):
                enabled = False
                entry = entry[9:].strip()
            elif entry_lower.startswith("[disabled]"):
                enabled = False
                entry = entry[10:].strip()
                
            name = ""
            key = ""
            
            paren_match = re.search(r'\s*[\(\[]([^\]\)]+)[\)\]]\s*$', entry)
            if paren_match:
                name = paren_match.group(1).strip()
                key = entry[:paren_match.start()].strip()
            elif ":" in entry:
                parts = entry.split(":", 1)
                name = parts[0].strip()
                key = parts[1].strip()
            else:
                key = entry.strip()
                
            if key:
                if not name and len(key.split()) > 1:
                    for sub_key in key.split():
                        sub_key = sub_key.strip()
                        if sub_key:
                            results.append({
                                "key": sub_key,
                                "name": "",
                                "enabled": enabled
                            })
                else:
                    results.append({
                        "key": key,
                        "name": name,
                        "enabled": enabled
                    })
        return results

    def _split_and_parse_keys(self, provider: str, val: str) -> List[str]:
        parsed = self._parse_all_keys(provider, val)
        keys = []
        for item in parsed:
            if item["enabled"]:
                key = item["key"]
                name = item["name"]
                if name:
                    self._key_names[(provider, key)] = name
                keys.append(key)
        return keys

    def _key_identifier(self, provider: str, api_key: str) -> str:
        if not api_key:
            return "empty key"
        name = self._key_names.get((provider, api_key))
        preview = api_key[-6:] if len(api_key) > 6 else api_key
        if name:
            return f"'{name}' (ending in ...{preview})"
        return f"ending in ...{preview}"

    def _api_keys_for(self, provider: str) -> List[str]:
        val = str(self._api_keys().get(provider, "") or "").strip()
        return self._split_and_parse_keys(provider, val)

    def _api_keys_for_custom(self, provider: str, custom_cfg: Dict[str, Any]) -> List[str]:
        val = str(custom_cfg.get("api_key", "") or "").strip()
        return self._split_and_parse_keys(provider, val)

    def _available_api_keys(self, provider: str) -> List[str]:
        keys = self._api_keys_for(provider)
        if not keys:
            return []
        
        now = time.time()
        available = []
        for key in keys:
            expiry = FAILED_KEYS_CACHE.get((provider, key))
            if expiry is None or now > expiry:
                if expiry is not None:
                    try:
                        del FAILED_KEYS_CACHE[(provider, key)]
                    except KeyError:
                        pass
                available.append(key)
        
        if not available:
            return keys
        return available

    def _mark_key_failed(self, provider: str, api_key: str, delay_seconds: float = None):
        if not api_key:
            return
        if delay_seconds is None:
            delay_seconds = self._cooldown_seconds()
        
        FAILED_KEYS_CACHE[(provider, api_key)] = time.time() + delay_seconds
        self._save_blacklist()
        key_id = self._key_identifier(provider, api_key)
        logger.info(f"AI-Hints: Key for {provider} ({key_id}) put on cooldown for {int(delay_seconds)}s due to failure.")

    def _on_key_success(self, provider: str, api_key: str):
        if not api_key:
            return
        key = (provider, api_key)
        if key in FAILED_KEYS_CACHE:
            try:
                del FAILED_KEYS_CACHE[key]
                self._save_blacklist()
                logger.debug(f"AI-Hints: Cleared cooldown for {provider} key {self._key_identifier(provider, api_key)}")
            except KeyError:
                pass


    def _get_model(self, provider: str) -> str:
        models = self.config.get("models") or {}
        if not isinstance(models, dict):
            models = {}
        model = models.get(provider, "") or DEFAULT_MODELS.get(provider, "")
        return self._normalize_model(provider, model)

    def _normalize_model(self, provider: str, model: str) -> str:
        model = str(model or "").strip()
        if provider == "gemini" and model.startswith("models/"):
            model = model.split("/", 1)[1]

        replacement = LEGACY_MODEL_REPLACEMENTS.get((provider, model))
        if replacement:
            logger.warning(
                f"AI-Hints: Replacing legacy {provider} model '{model}' with '{replacement}'."
            )
            return replacement
        return model

    def _is_actually_online(self) -> bool:
        """
        Returns True if the network is currently available.
        Uses a cached value updated by a background thread, but performs
        a synchronous refresh if the cache is older than 60 seconds.
        """
        now = time.time()
        if now - _NETWORK_STATE["last_check"] < 60:
            return _NETWORK_STATE["online"]
        return _check_network_online()

    def _cooldown_seconds(self) -> float:
        return self.config.get("model_cooldown_minutes", 10) * 60

    def _mark_model_failed(self, provider: str, model: str, delay_seconds: float = None):
        """Records a model failure and sets a cooldown timer."""
        # Only blacklist if we are actually online. If the network is down, 
        # the failure is likely due to connectivity, not the specific model/provider.
        if not self._is_actually_online():
            logger.info(f"AI-Hints: Skipping blacklist for {provider}/{model} because network appears offline.")
            return

        if delay_seconds is None:
            # Apply streak-based cooldown for ALL failures to prevent repeated lag
            key = (provider, model)
            streak = RATE_LIMIT_STREAK.get(key, 0) + 1
            RATE_LIMIT_STREAK[key] = streak

            cooldown_sec = self._cooldown_seconds()
            delay_seconds = cooldown_sec * streak
            
        expiry = time.time() + delay_seconds
        FAILED_MODELS_CACHE[(provider, model)] = expiry
        self._save_blacklist()
        
        # Format for log
        mins = int(delay_seconds // 60)
        hours = mins // 60
        mins = mins % 60
        secs = int(delay_seconds % 60)
        
        if hours > 0:
            time_str = f"{hours}h {mins}m"
        elif mins > 0:
            time_str = f"{mins}m {secs}s"
        else:
            time_str = f"{secs}s"
            
        logger.info(f"AI-Hints: Blacklisting {provider}/{model} for {time_str} due to failure (Streak: {RATE_LIMIT_STREAK.get((provider, model), 1)}).")

    def _on_model_success(self, provider: str, model: str):
        """Resets the rate limit streak when a model successfully responds."""
        logger.info(f"AI-Hints: Successful generation response from {provider} using model {model}.")
        key = (provider, model)
        needs_save = False
        if key in RATE_LIMIT_STREAK:
            logger.debug(f"AI-Hints: Resetting failure streak for {provider}/{model} after success.")
            del RATE_LIMIT_STREAK[key]
            needs_save = True
        
        # If it was blacklisted, remove it
        if key in FAILED_MODELS_CACHE:
            del FAILED_MODELS_CACHE[key]
            needs_save = True
            
        if needs_save:
            self._save_blacklist()

    def _is_model_failed(self, provider: str, model: str) -> bool:
        """Returns True if the model is currently in its cooldown period."""
        global _BLACKLIST_LOADED
        if not _BLACKLIST_LOADED and not FAILED_MODELS_CACHE:
            self._load_blacklist()
            
        expiry = FAILED_MODELS_CACHE.get((provider, model))
        if expiry is None:
            return False
        
        if time.time() > expiry:
            # Cooldown expired, remove from cache
            del FAILED_MODELS_CACHE[(provider, model)]
            self._save_blacklist()
            return False
            
        return True

    def _save_blacklist(self):
        """Persists the FAILED_MODELS_CACHE, FAILED_KEYS_CACHE and RATE_LIMIT_STREAK to disk."""
        try:
            # Convert tuple keys to strings for JSON
            expiries = {f"{p}|{m}": e for (p, m), e in FAILED_MODELS_CACHE.items()}
            streaks = {f"{p}|{m}": s for (p, m), s in RATE_LIMIT_STREAK.items()}
            keys_expiries = {f"{p}|{k}": e for (p, k), e in FAILED_KEYS_CACHE.items()}
            
            # Save as a nested structure
            data = {
                "expiries": expiries,
                "streaks": streaks,
                "keys_expiries": keys_expiries,
                "version": 2
            }
            
            with open(BLACKLIST_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"AI-Hints: Failed to save blacklist: {e}")

    def _load_blacklist(self):
        """Loads the FAILED_MODELS_CACHE, FAILED_KEYS_CACHE and RATE_LIMIT_STREAK from disk."""
        global _BLACKLIST_LOADED
        _BLACKLIST_LOADED = True
        if not os.path.exists(BLACKLIST_FILE):
            return
        try:
            with open(BLACKLIST_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            now = time.time()
            
            # Clear existing memory caches to stay in sync with disk
            FAILED_MODELS_CACHE.clear()
            RATE_LIMIT_STREAK.clear()
            FAILED_KEYS_CACHE.clear()

            # Check if it's the new format or old flat format
            if isinstance(data, dict) and "expiries" in data:
                # New format (version 2)
                expiries = data.get("expiries", {})
                streaks = data.get("streaks", {})
                keys_expiries = data.get("keys_expiries", {})
                
                for key, expiry in expiries.items():
                    if "|" in key and expiry > now:
                        provider, model = key.split("|", 1)
                        FAILED_MODELS_CACHE[(provider, model)] = expiry
                
                for key, streak in streaks.items():
                    if "|" in key:
                        provider, model = key.split("|", 1)
                        RATE_LIMIT_STREAK[(provider, model)] = streak

                for key, expiry in keys_expiries.items():
                    if "|" in key and expiry > now:
                        provider, api_key = key.split("|", 1)
                        FAILED_KEYS_CACHE[(provider, api_key)] = expiry
            else:
                # Old flat format (just expiries)
                for key, expiry in data.items():
                    if "|" in key and isinstance(expiry, (int, float)) and expiry > now:
                        provider, model = key.split("|", 1)
                        FAILED_MODELS_CACHE[(provider, model)] = expiry
        except Exception as e:
            logger.error(f"AI-Hints: Failed to load blacklist: {e}")

    def _extract_retry_delay(self, provider: str, model: str, error: urllib.error.HTTPError, body: str) -> float:
        """
        Calculates cooldown delay.
        For 429 (rate limit), we respect any Retry-After header or use streak-based logic.
        """
        # For non-429, we let _mark_model_failed handle the streak-based cooldown
        if getattr(error, "code", None) != 429:
            return None
            
        cooldown_sec = self._cooldown_seconds()
        key = (provider, model)
        streak = RATE_LIMIT_STREAK.get(key, 0) + 1
        RATE_LIMIT_STREAK[key] = streak
        
        # delay = cooldown * streak
        delay = cooldown_sec * streak
        logger.info(f"AI-Hints: Rate limit (429) hit for {provider}/{model}. Streak: {streak}. New delay: {delay/60:.1f} minutes.")
        return delay

    def _models_for_provider(self, provider: str, primary_model: str = "", extra_fallbacks: List[str] = None) -> List[str]:
        configured = self.config.get("model_fallbacks") or {}
        if not isinstance(configured, dict):
            configured = {}
        configured_fallbacks = self._model_list(configured.get(provider, []))
        from .logger import log_context
        if getattr(log_context, "source", None) == "model_test":
            candidates = [
                primary_model or self._get_model(provider),
            ]
        else:
            candidates = [
                primary_model or self._get_model(provider),
                *self._model_list(extra_fallbacks),
                *configured_fallbacks,
            ]

        disabled_fallback = self.config.get("disabled_fallback_models") or {}
        disabled_models = disabled_fallback.get(provider, [])
        if not isinstance(disabled_models, list):
            disabled_models = []

        models = []
        seen = set()
        for candidate in candidates:
            if getattr(log_context, "source", None) != "model_test" and candidate in disabled_models:
                continue
            model = self._normalize_model(provider, candidate)
            if not model or model in seen:
                continue
            if getattr(log_context, "source", None) != "model_test" and model in disabled_models:
                continue
            seen.add(model)
            
            # Skip if model is blacklisted
            if getattr(log_context, "source", None) != "model_test" and self._is_model_failed(provider, model):
                logger.debug(f"AI-Hints: Skipping blacklisted model {provider}/{model}.")
                continue
                
            models.append(model)
            
        return models

    def _model_list(self, value: Any) -> List[str]:
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            return value
        return []

    def _log_model_attempt(self, provider: str, model: str, models: List[str]) -> None:
        if models and model != models[0]:
            logger.debug(f"AI-Hints: Trying fallback model for {provider}: {model}")
        else:
            logger.debug(f"AI-Hints: Calling {provider} with model: {model}")

    def _json_headers(self, api_key: str = "") -> Dict[str, str]:
        api_key = str(api_key or "").strip()
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    def fetch_models(self, provider: str) -> List[str]:
        """Fetch available models from the provider's API."""
        if provider in ["local", "antigravity"]:
            keys = [""]
        else:
            keys = self._available_api_keys(provider)
            custom_providers = self.config.get("custom_providers", {}) or {}
            if not keys and provider in custom_providers:
                keys = self._api_keys_for_custom(provider, custom_providers[provider])
            if not keys:
                return []

        last_err = None
        for api_key in keys:
            try:
                if provider == "openrouter":
                    url = "https://openrouter.ai/api/v1/models"
                    headers = self._json_headers(api_key)
                    result = self._get_json(url, headers)
                    self._on_key_success(provider, api_key)
                    return [m.get("id") for m in result.get("data", []) if m.get("id")]
                
                elif provider == "gemini":
                    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
                    result = self._get_json(url, {})
                    models = []
                    for m in result.get("models", []):
                        name = m.get("name", "")
                        if "generateContent" in m.get("supportedGenerationMethods", []):
                            if name.startswith("models/"):
                                name = name[7:]
                            models.append(name)
                    self._on_key_success(provider, api_key)
                    return models

                elif provider == "groq":
                    url = "https://api.groq.com/openai/v1/models"
                    headers = self._json_headers(api_key)
                    result = self._get_json(url, headers)
                    self._on_key_success(provider, api_key)
                    return [m.get("id") for m in result.get("data", []) if m.get("id")]

                elif provider == "local":
                    local_cfg = self.config.get("local_endpoint") or {}
                    base_url = str(local_cfg.get("base_url", "http://localhost:11434/v1")).rstrip("/")
                    url = f"{base_url}/models"
                    headers = self._json_headers(local_cfg.get("api_key", ""))
                    result = self._get_json(url, headers)
                    return [m.get("id") for m in result.get("data", []) if m.get("id")]

                elif provider == "antigravity":
                    ag_cfg = self.config.get("antigravity_proxy") or {}
                    port = ag_cfg.get("port", 3000)
                    url = f"http://localhost:{port}/v1/models"
                    headers = self._json_headers("antigravity")
                    result = self._get_json(url, headers)
                    return [m.get("id") for m in result.get("data", []) if m.get("id")]

                # Generic OpenAI-compatible providers
                openai_style = ["openai", "deepseek", "mistral", "together", "nvidia", "sambanova", "cerebras", "grok"]
                if provider in openai_style:
                    urls = {
                        "openai": "https://api.openai.com/v1/models",
                        "deepseek": "https://api.deepseek.com/models",
                        "mistral": "https://api.mistral.ai/v1/models",
                        "together": "https://api.together.xyz/v1/models",
                        "nvidia": "https://integrate.api.nvidia.com/v1/models",
                        "sambanova": "https://api.sambanova.ai/v1/models",
                        "cerebras": "https://api.cerebras.ai/v1/models",
                        "grok": "https://api.x.ai/v1/models",
                    }
                    url = urls.get(provider)
                    if url:
                        headers = self._json_headers(api_key)
                        result = self._get_json(url, headers)
                        self._on_key_success(provider, api_key)
                        return [m.get("id") for m in result.get("data", []) if m.get("id")]

                elif provider == "huggingface":
                    return MODEL_SUGGESTIONS.get("huggingface", [])

                # Custom providers
                custom_providers = self.config.get("custom_providers", {}) or {}
                if provider in custom_providers:
                    custom_cfg = custom_providers[provider]
                    url = str(custom_cfg.get("url", "") or "").strip()
                    if url:
                        models_url = url
                        if models_url.endswith("/chat/completions"):
                            models_url = models_url.replace("/chat/completions", "/models")
                        elif not models_url.endswith("/models"):
                            models_url = models_url.rstrip("/") + "/models"
                        
                        custom_headers = custom_cfg.get("headers", {})
                        headers = self._json_headers(api_key)
                        if isinstance(custom_headers, dict):
                            headers.update(custom_headers)
                        
                        result = self._get_json(models_url, headers)
                        self._on_key_success(provider, api_key)
                        return [m.get("id") for m in result.get("data", []) if m.get("id")]

            except Exception as e:
                self._mark_key_failed(provider, api_key)
                last_err = e
                continue
        if last_err:
            logger.error(f"AI-Hints: Failed to fetch models for {provider}: {last_err}")
        return []

    def _get_json(self, url: str, headers: Dict[str, str]) -> Dict[str, Any]:
        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))

    def _post_json(self, url: str, data: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
        body = json.dumps(self._drop_none(data)).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))

    def _drop_none(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {k: self._drop_none(v) for k, v in value.items() if v is not None}
        if isinstance(value, list):
            return [self._drop_none(v) for v in value]
        return value

    def _extract_content(self, result: Any) -> str:
        if not isinstance(result, dict):
            return str(result)

        choices = result.get("choices")
        if choices:
            first = choices[0]
            message = first.get("message", {}) if isinstance(first, dict) else {}
            content = message.get("content")
            if content is not None:
                return content if isinstance(content, str) else json.dumps(content)
            text = first.get("text") if isinstance(first, dict) else None
            if text is not None:
                return text

        content = result.get("content")
        if isinstance(content, list) and content:
            text_parts = []
            for part in content:
                if isinstance(part, dict) and part.get("text"):
                    text_parts.append(part["text"])
            if text_parts:
                return "\n".join(text_parts)
        elif isinstance(content, str):
            return content

        candidates = result.get("candidates")
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            # Filter out thought components if Gemini returned explicit thoughts
            text_parts = [
                part.get("text", "") 
                for part in parts 
                if isinstance(part, dict) and not part.get("thought")
            ]
            if text_parts:
                return "\n".join(text_parts)

        if "hints" in result or "options" in result:
            return json.dumps(result)
        return str(result)

    def _normalize_string_list(self, value: Any) -> List[str]:
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            return []

        normalized = []
        for item in value:
            if item is None:
                continue
            text = str(item).strip()
            if text:
                text = self._clean_ai_math_output(text)
                normalized.append(text)
        return normalized

    def _clean_ai_math_output(self, text: str) -> str:
        if not text:
            return ""
        
        # 1. Strip trailing JSON or technical metadata hallucinations
        # (e.g. "Answer: C {"hints": [...], "options": [...]} ")
        # We look for a trailing { ... } that contains technical keys.
        # We use \\* to match any number of backslashes before the quote (escaped JSON).
        text = re.sub(r'\s*\{[\s\S]*\\*"(?:hints|options|c\d+)\\*"\s*:[\s\S]*\}\s*$', '', text)
        
        # 2. Strip "Answer: " or "Option: " prefixes if AI included them
        text = re.sub(r'^(?:Answer|Option|Hint|Choice)\s*:\s*', '', text, flags=re.IGNORECASE)

        # 3. Fix double backslashes for delimiters: \\( -> \(
        # Many models over-escape in JSON context, especially after our repair logic.
        text = text.replace('\\\\(', '\\(').replace('\\\\)', '\\)')
        text = text.replace('\\\\[', '\\[').replace('\\\\]', '\\]')

        # 4. Fix nested parentheses: \( ( ... ) \) -> \( ... \)
        # This happens when the AI wraps the entire equation in redundant parentheses.
        # We handle whitespace carefully.
        text = re.sub(r'\\\(\s*\(\s*(.*?)\s*\)\s*\\\)', r'\(\1\)', text)
        text = re.sub(r'\\\[\s*\(\s*(.*?)\s*\)\s*\\\]', r'\[\1\]', text)
        
        return text

    def _read_http_error(self, error: urllib.error.HTTPError) -> str:
        try:
            body = error.read().decode("utf-8", errors="replace")
        except Exception:
            return ""
        return body[:4000]

def load_blacklist():
    """Globally loads the blacklist into memory caches."""
    client = AIClient(None)
    client._load_blacklist()

def is_model_blacklisted(provider: str, model: str) -> bool:
    try:
        global _BLACKLIST_LOADED
        if not _BLACKLIST_LOADED and not FAILED_MODELS_CACHE:
            load_blacklist()
        client = AIClient(None)
        return client._is_model_failed(provider, model)
    except Exception:
        return False
