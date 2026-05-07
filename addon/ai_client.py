import json
import urllib.request
import urllib.error
import urllib.parse
from typing import List, Dict, Any
from .logger import logger

REQUEST_TIMEOUT_SECONDS = 60
USER_AGENT = "Anki-AI-Hints/1.0"

PROVIDER_ORDER = [
    "gemini",
    "groq",
    "openrouter",
    "sambanova",
    "cerebras",
    "huggingface",
    "openai",
    "anthropic",
    "deepseek",
    "mistral",
    "together",
    "nvidia",
    "grok",
    "local",
]

DEFAULT_MODELS = {
    "openai":     "gpt-4o-mini",
    "anthropic":  "claude-3-5-haiku-20241022",
    "gemini":     "gemini-2.5-flash",
    "groq":       "llama-3.1-8b-instant",
    "deepseek":   "deepseek-chat",
    "grok":       "grok-3-mini",
    "mistral":    "mistral-small-latest",
    "openrouter": "meta-llama/llama-3.1-8b-instruct",
    "nvidia":     "meta/llama-3.1-8b-instruct",
    "huggingface": "meta-llama/Llama-3.1-8B-Instruct",
    "together":   "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo",
    "sambanova":  "Meta-Llama-3.1-8B-Instruct",
    "cerebras":   "llama3.1-8b",
    "local":      "llama3",
}

LEGACY_MODEL_REPLACEMENTS = {
    ("anthropic", "claude-3-haiku-20240307"): "claude-3-5-haiku-20241022",
    ("gemini", "gemini-1.5-flash"): "gemini-2.5-flash",
    ("gemini", "models/gemini-1.5-flash"): "gemini-2.5-flash",
    ("groq", "llama3-8b-8192"): "llama-3.1-8b-instant",
    ("groq", "llama3-70b-8192"): "llama-3.3-70b-versatile",
    ("grok", "grok-1"): "grok-3-mini",
    ("huggingface", "meta-llama/Meta-Llama-3-8B-Instruct"): "meta-llama/Llama-3.1-8B-Instruct",
    ("nvidia", "meta/llama3-8b-instruct"): "meta/llama-3.1-8b-instruct",
    ("openrouter", "meta-llama/llama-3-8b-instruct"): "meta-llama/llama-3.1-8b-instruct",
    ("together", "mistralai/Mixtral-8x7B-Instruct-v0.1"): "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo",
}

class AIClient:
    def __init__(self, config: Dict[str, Any]):
        self.config = config or {}

    def generate_options(self, front: str, back: str) -> Dict[str, List[str]]:
        primary_provider = self.config.get("ai_provider", "openai")
        system_prompt = (self.config.get("system_prompt", "") or "").strip()
        count = self._options_count()
        
        # Add strict formatting every time; user-provided prompts often omit the exact count.
        system_prompt = (
            f"{system_prompt}\n\n" if system_prompt else ""
        ) + (
            "Return only valid JSON with two array keys: hints and options. "
            f"Generate exactly {count} plausible options and 2-3 helpful hints. "
            "Do not include the correct answer in options."
        )
        prompt = f"Front: {front}\nBack: {back}" if back else f"Content: {front}"

        all_potential = self._candidate_providers(primary_provider)
        if not all_potential:
            logger.error("AI-Hints: No configured AI provider is ready.")
            return {"hints": [], "options": []}
        
        # Try providers in sequence
        for provider in all_potential:
            try:
                logger.info(f"Attempting to generate hints using provider: {provider}")
                result = self._call_provider(provider, system_prompt, prompt)
                if result.get("hints") or result.get("options"):
                    if provider != primary_provider:
                        logger.info(f"Fallback successful using provider: {provider}")
                    return result
            except Exception as e:
                logger.error(f"Provider {provider} failed: {e}")
                continue
                
        return {"hints": [], "options": []}

    def has_ready_provider(self, provider: str) -> bool:
        return self._is_provider_ready(provider, primary=True)

    def has_any_ready_provider(self) -> bool:
        primary = self.config.get("ai_provider", "openai")
        return bool(self._candidate_providers(primary))

    def _candidate_providers(self, primary_provider: str) -> List[str]:
        custom_providers = list((self.config.get("custom_providers") or {}).keys())
        candidates = []

        if self._is_provider_ready(primary_provider, primary=True):
            candidates.append(primary_provider)
        else:
            logger.warning(
                f"AI-Hints: Primary provider '{primary_provider}' is not configured; checking fallbacks."
            )

        for provider in PROVIDER_ORDER + custom_providers:
            if provider == primary_provider or provider in candidates:
                continue
            if self._is_provider_ready(provider, primary=False):
                candidates.append(provider)
        return candidates

    def _is_provider_ready(self, provider: str, primary: bool = False) -> bool:
        if provider == "local":
            local_cfg = self.config.get("local_endpoint") or {}
            if primary:
                return True
            return bool(local_cfg.get("enabled", False))

        custom_providers = self.config.get("custom_providers") or {}
        if provider in custom_providers:
            custom_cfg = custom_providers[provider]
            return bool(custom_cfg.get("url", "").strip() and custom_cfg.get("model", "").strip())

        return bool((self.config.get("api_keys") or {}).get(provider, "").strip())

    def _call_provider(self, provider: str, system_prompt: str, prompt: str) -> Dict[str, List[str]]:
        custom_providers = self.config.get("custom_providers") or {}
        if provider == "anthropic":
            return self._call_anthropic(system_prompt, prompt)
        elif provider == "gemini":
            return self._call_gemini(system_prompt, prompt)
        elif provider in custom_providers:
            return self._call_custom_provider(provider, system_prompt, prompt)
        else:
            return self._call_openai_compatible(provider, system_prompt, prompt)

    def _call_custom_provider(self, provider_name: str, system_prompt: str, prompt: str) -> Dict[str, List[str]]:
        custom_cfg = (self.config.get("custom_providers") or {}).get(provider_name, {})
        url = custom_cfg.get("url", "")
        api_key = custom_cfg.get("api_key", "").strip()
        model = custom_cfg.get("model", "")
        custom_headers = custom_cfg.get("headers", {})

        headers = self._json_headers(api_key)
        headers.update(custom_headers)

        data = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ]
        }

        try:
            result = self._post_json(url, data, headers)
            content = self._extract_content(result)
            return self._parse_json_result(content)
        except urllib.error.HTTPError as e:
            logger.error(f"AI-Hints Error (Custom Provider {provider_name}): {e} - {self._read_http_error(e)}")
            return {"hints": [], "options": []}
        except Exception as e:
            logger.error(f"AI-Hints Error (Custom Provider {provider_name}): {e}")
            return {"hints": [], "options": []}

    def _call_openai_compatible(self, provider: str, system_prompt: str, prompt: str) -> Dict[str, List[str]]:
        api_key = (self.config.get("api_keys") or {}).get(provider, "").strip()
        model = self._get_model(provider)
        
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
            base_url = local_cfg.get("base_url", "http://localhost:11434/v1")
            model = (local_cfg.get("model", "") or model or DEFAULT_MODELS["local"]).strip()
            api_key = (local_cfg.get("api_key", "") or api_key).strip()
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
        
        headers = self._json_headers(api_key)
        
        if provider == "openrouter":
            headers["HTTP-Referer"] = "https://github.com/athulkrishna2015/ai-hints"
            headers["X-Title"] = "Anki AI-Hints"

        data = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
        }
        if provider in ["openai", "groq", "deepseek", "mistral"]:
            data["response_format"] = {"type": "json_object"}

        try:
            result = self._post_json(url, data, headers)
            content = self._extract_content(result)
            return self._parse_json_result(content)
        except urllib.error.HTTPError as e:
            logger.error(f"AI-Hints Error ({provider}): {e} - {self._read_http_error(e)}")
            return {"hints": [], "options": []}
        except Exception as e:
            logger.error(f"AI-Hints Error ({provider}): {e}")
            return {"hints": [], "options": []}

    def _call_anthropic(self, system_prompt: str, prompt: str) -> Dict[str, List[str]]:
        api_key = (self.config.get("api_keys") or {}).get("anthropic", "").strip()
        model = self._get_model("anthropic")
        url = "https://api.anthropic.com/v1/messages"
        
        headers = self._json_headers()
        headers.update({
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01"
        })
        
        data = {
            "model": model,
            "system": system_prompt,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1024
        }
        
        try:
            result = self._post_json(url, data, headers)
            content = self._extract_content(result)
            return self._parse_json_result(content)
        except urllib.error.HTTPError as e:
            logger.error(f"AI-Hints Error (Anthropic): {e} - {self._read_http_error(e)}")
            return {"hints": [], "options": []}
        except Exception as e:
            logger.error(f"AI-Hints Error (Anthropic): {e}")
            return {"hints": [], "options": []}

    def _call_gemini(self, system_prompt: str, prompt: str) -> Dict[str, List[str]]:
        api_key = (self.config.get("api_keys") or {}).get("gemini", "").strip()
        model = self._get_model("gemini")
        model_path = urllib.parse.quote(model, safe="")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_path}:generateContent"
        logger.debug(f"Calling Gemini with model: {model}")
        
        headers = self._json_headers()
        headers["x-goog-api-key"] = api_key
        
        data = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseJsonSchema": {
                    "type": "object",
                    "properties": {
                        "hints": {"type": "array", "items": {"type": "string"}},
                        "options": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["hints", "options"],
                },
            },
        }
        
        try:
            result = self._post_json(url, data, headers)
            content = self._extract_content(result)
            return self._parse_json_result(content)
        except urllib.error.HTTPError as e:
            logger.error(f"AI-Hints Error (Gemini): {e} - {self._read_http_error(e)}")
            return {"hints": [], "options": []}
        except Exception as e:
            logger.error(f"AI-Hints Error (Gemini): {e}")
            return {"hints": [], "options": []}

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
            parsed = json.loads(content)
        except json.JSONDecodeError:
            start = content.find("{")
            end = content.rfind("}")
            if start == -1 or end == -1 or end <= start:
                logger.warning("AI-Hints: Provider response did not contain JSON.")
                return {"hints": [], "options": []}
            try:
                parsed = json.loads(content[start:end + 1])
            except json.JSONDecodeError:
                logger.warning("AI-Hints: Provider response contained invalid JSON.")
                return {"hints": [], "options": []}

        if not isinstance(parsed, dict):
            return {"hints": [], "options": []}

        return {
            "hints": self._normalize_string_list(parsed.get("hints", [])),
            "options": self._normalize_string_list(parsed.get("options", []))[:self._options_count()],
        }

    def _options_count(self) -> int:
        try:
            count = int(self.config.get("options_count", 4))
        except (TypeError, ValueError):
            count = 4
        return max(1, min(count, 10))

    def _get_model(self, provider: str) -> str:
        model = ((self.config.get("models") or {}).get(provider, "") or DEFAULT_MODELS.get(provider, "")).strip()
        if provider == "gemini" and model.startswith("models/"):
            model = model.split("/", 1)[1]

        replacement = LEGACY_MODEL_REPLACEMENTS.get((provider, model))
        if replacement:
            logger.warning(
                f"AI-Hints: Replacing legacy {provider} model '{model}' with '{replacement}'."
            )
            return replacement
        return model

    def _json_headers(self, api_key: str = "") -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

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
            text_parts = [part.get("text", "") for part in parts if isinstance(part, dict)]
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
                normalized.append(text)
        return normalized

    def _read_http_error(self, error: urllib.error.HTTPError) -> str:
        try:
            body = error.read().decode("utf-8", errors="replace")
        except Exception:
            return ""
        return body[:4000]
