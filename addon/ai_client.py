import json
import urllib.request
import urllib.error
from typing import List, Optional, Dict, Any
from .logger import logger

DEFAULT_MODELS = {
    "openai":     "gpt-4o-mini",
    "anthropic":  "claude-3-haiku-20240307",
    "gemini":     "gemini-1.5-flash",
    "groq":       "llama3-8b-8192",
    "deepseek":   "deepseek-chat",
    "grok":       "grok-2-latest",
    "mistral":    "mistral-small-latest",
    "openrouter": "meta-llama/llama-3-8b-instruct",
    "nvidia":     "meta/llama3-8b-instruct",
}

class AIClient:
    def __init__(self, config: Dict[str, Any]):
        self.config = config

    def generate_options(self, front: str, back: str) -> Dict[str, List[str]]:
        provider = self.config.get("ai_provider", "openai")
        system_prompt = self.config.get("system_prompt", "")
        count = self.config.get("options_count", 4)
        
        # Append specific count instruction
        system_prompt += f" Precisely generate exactly {count} options and 2-3 helpful hints."
        
        prompt = f"Front: {front}\nBack: {back}" if back else f"Content: {front}"
        
        custom_providers = self.config.get("custom_providers", {})
        
        if provider == "anthropic":
            return self._call_anthropic(system_prompt, prompt)
        elif provider == "gemini":
            return self._call_gemini(system_prompt, prompt)
        elif provider in custom_providers:
            return self._call_custom_provider(provider, system_prompt, prompt)
        else:
            # Covers openai, deepseek, groq, nvidia, grok, openrouter, local, mistral
            return self._call_openai_compatible(provider, system_prompt, prompt)

    def _call_custom_provider(self, provider_name: str, system_prompt: str, prompt: str) -> Dict[str, List[str]]:
        custom_cfg = self.config.get("custom_providers", {}).get(provider_name, {})
        url = custom_cfg.get("url", "")
        api_key = custom_cfg.get("api_key", "")
        model = custom_cfg.get("model", "")
        custom_headers = custom_cfg.get("headers", {})

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        headers.update(custom_headers)

        data = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ]
        }

        try:
            req = urllib.request.Request(url, data=json.dumps(data).encode("utf-8"), headers=headers)
            with urllib.request.urlopen(req) as response:
                result = json.loads(response.read().decode("utf-8"))
                # Try OpenAI format first
                if "choices" in result:
                    content = result["choices"][0]["message"]["content"]
                else:
                    # Generic fallback
                    content = str(result)
                return self._parse_json_result(content)
        except Exception as e:
            logger.error(f"AI-Hints Error (Custom Provider {provider_name}): {e}")
            return {"hints": [], "options": []}

    def _call_openai_compatible(self, provider: str, system_prompt: str, prompt: str) -> Dict[str, List[str]]:
        api_key = self.config.get("api_keys", {}).get(provider, "")
        model = self.config.get("models", {}).get(provider, "") or DEFAULT_MODELS.get(provider, "")
        
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
            local_cfg = self.config.get("local_endpoint", {})
            base_url = local_cfg.get("base_url", "http://localhost:11434/v1")
            model = local_cfg.get("model", model)
        elif provider == "mistral":
            base_url = "https://api.mistral.ai/v1"
        
        url = f"{base_url}/chat/completions"
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        
        if provider == "openrouter":
            headers["HTTP-Referer"] = "https://github.com/athulkrishna2015/ai-hints"
            headers["X-Title"] = "Anki AI-Hints"

        data = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            "response_format": {"type": "json_object"} if provider in ["openai", "groq", "deepseek", "mistral"] else None
        }

        try:
            req = urllib.request.Request(url, data=json.dumps(data).encode("utf-8"), headers=headers)
            with urllib.request.urlopen(req) as response:
                result = json.loads(response.read().decode("utf-8"))
                content = result["choices"][0]["message"]["content"]
                return self._parse_json_result(content)
        except Exception as e:
            logger.error(f"AI-Hints Error ({provider}): {e}")
            return {"hints": [], "options": []}

    def _call_anthropic(self, system_prompt: str, prompt: str) -> Dict[str, List[str]]:
        api_key = self.config.get("api_keys", {}).get("anthropic", "")
        model = self.config.get("models", {}).get("anthropic", "")
        url = "https://api.anthropic.com/v1/messages"
        
        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01"
        }
        
        data = {
            "model": model,
            "system": system_prompt,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1024
        }
        
        try:
            req = urllib.request.Request(url, data=json.dumps(data).encode("utf-8"), headers=headers)
            with urllib.request.urlopen(req) as response:
                result = json.loads(response.read().decode("utf-8"))
                content = result["content"][0]["text"]
                return self._parse_json_result(content)
        except Exception as e:
            logger.error(f"AI-Hints Error (Anthropic): {e}")
            return {"hints": [], "options": []}

    def _call_gemini(self, system_prompt: str, prompt: str) -> Dict[str, List[str]]:
        api_key = self.config.get("api_keys", {}).get("gemini", "")
        model = self.config.get("models", {}).get("gemini", "") or DEFAULT_MODELS["gemini"]
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        logger.debug(f"Calling Gemini with model: {model}")
        
        headers = {"Content-Type": "application/json"}
        
        full_prompt = f"{system_prompt}\n\n{prompt}"
        
        data = {
            "contents": [{"parts": [{"text": full_prompt}]}]
        }
        
        try:
            req = urllib.request.Request(url, data=json.dumps(data).encode("utf-8"), headers=headers)
            with urllib.request.urlopen(req) as response:
                result = json.loads(response.read().decode("utf-8"))
                content = result["candidates"][0]["content"]["parts"][0]["text"]
                return self._parse_json_result(content)
        except Exception as e:
            logger.error(f"AI-Hints Error (Gemini): {e}")
            return {"hints": [], "options": []}

    def _parse_json_result(self, content: str) -> Dict[str, List[str]]:
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                return {
                    "hints": parsed.get("hints", []),
                    "options": parsed.get("options", [])
                }
            return {"hints": [], "options": []}
        except:
            return {"hints": [], "options": []}
