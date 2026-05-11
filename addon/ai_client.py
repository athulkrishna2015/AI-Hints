import json
import re
import html
import urllib.request
import urllib.error
import urllib.parse
from typing import List, Dict, Any
from .logger import logger

try:
    from .json_repair import loads as repair_loads
except ImportError:
    repair_loads = json.loads

REQUEST_TIMEOUT_SECONDS = 20
USER_AGENT = "Anki-AI-Hints/1.0"
GEMINI_PROVIDER_EXHAUSTED_STATUSES = {429}

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
    "local",
]

DEFAULT_MODELS = {
    "openai":     "gpt-4o",
    "anthropic":  "claude-3-7-sonnet-latest",
    "gemini":     "gemini-3-flash-preview",
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
        "gemini-3-flash-preview",
        "gemini-3.1-flash-lite-preview",
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite-preview-02-05",
        "gemini-2.0-pro-exp-02-05",
        "gemini-1.5-flash",
        "gemini-1.5-pro",
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
        "openai/gpt-4o-mini",
        "anthropic/claude-3.5-haiku",
        "deepseek/deepseek-chat",
        "meta-llama/llama-3.3-70b-instruct",
        "google/gemini-2.0-flash-exp:free",
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
}

LEGACY_MODEL_REPLACEMENTS = {
    ("anthropic", "claude-3-haiku-20240307"): "claude-3-5-haiku-latest",
    ("gemini", "gemini-1.5-flash"): "gemini-2.0-flash",
    ("gemini", "models/gemini-1.5-flash"): "gemini-2.0-flash",
    ("gemini", "models/gemini-2.0-flash-exp"): "gemini-2.0-flash",
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
        "gemini-flash-latest",
        "gemini-3-flash-preview",
        "gemini-3.1-flash-lite-preview",
        "gemini-2.0-pro-exp-02-05",
        "gemini-1.5-pro",
        "gemini-2.0-flash",
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
        "anthropic/claude-3.5-sonnet",
        "openai/gpt-4o",
        "deepseek/deepseek-chat",
        "meta-llama/llama-3.3-70b-instruct",
        "meta-llama/llama-3.3-70b-instruct:free",
        "google/gemini-2.0-flash-001",
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
            "CRITICAL: You are an Anki flashcard assistant. Your sole purpose is to generate multiple-choice options and hints.\n\n"
            "OUTPUT FORMAT:\n"
            "- Return strictly valid, raw JSON. DO NOT include any text outside the JSON block. No preambles, no markdown wrappers.\n"
            "- DO NOT include technical keys, JSON structures, or metadata inside the actual string values.\n"
            f"- Generate exactly {count} options/distractors total and 2-3 helpful hints.\n"
            "- If your output JSON uses an 'options' array, it MUST include the exact correct answer provided. If it uses 'distractors', provide only incorrect ones.\n"
            "- All incorrect options/distractors must be highly plausible, challenging, and target common misconceptions.\n\n"
            "CONTENT RULES:\n"
            "1. NO REPETITION: Do NOT repeat the question, front text, or the prompt itself in the hints or options.\n"
            "2. DEDUPLICATE: All options must be mathematically and textually distinct. Never provide the same value in different formats.\n"
            "3. UNIFORMITY: Distractors MUST perfectly match the format, grammar, length, and style of the correct answer.\n"
            "4. CLOZE CONTEXT: If 'Current cloze deletion' is provided, options MUST be full meaningful words or equations, not just the missing fragment. For example, for '{{c1::anti}}ferromagnet', output 'antiferromagnet' (not 'anti'). For '\\(F = {{c1::ma}}\\)', output '\\(F = ma\\)' (not '\\(ma\\)').\n"
            "5. MULTI-CLOZE HANDLING: For multiple clozes with the same ID, each option MUST be a comma-separated list of values (e.g., 'val1, val2') corresponding to each cloze in order.\n"
            "6. NO VERBATIM HINTS: Hints must provide underlying principles, mnemonics, or contextual clues. Never repeat card content verbatim.\n"
            "7. CONCISE: Keep hints short, specific, and focused. Avoid wordy explanations.\n\n"
            "FORMATTING & LATEX RULES:\n"
            "1. NO CLOZE SYNTAX: DO NOT output Anki cloze syntax (e.g., {{c1::...}}). Provide only plain text or math.\n"
            "2. MATH DELIMITERS: USE ONLY $ ... $ for inline math and $$ ... $$ for block math. DO NOT use \\( or \\[. DO NOT wrap $ inside other delimiters.\n"
            "3. UNIFORM MATH: All options MUST use the exact same mathematical delimiter type. Do not mix $ and $$ across options.\n"
            "4. JSON ESCAPING: Properly escape all quotation marks and backslashes (\\\\) so the output parses perfectly as JSON.\n"
        )
        prompt = f"Front: {front}\nBack / correct answer: {back}" if back else f"Content: {front}"

        all_potential = self._candidate_providers(primary_provider)
        if not all_potential:
            logger.error("AI-Hints: No configured AI provider is ready.")
            return {"hints": [], "options": []}
        
        last_exception = None
        # Try providers in sequence
        for provider in all_potential:
            try:
                result = self._call_provider(provider, system_prompt, prompt)
                if result.get("hints") or result.get("options") or result.get("distractors") or result.get("correct_answer"):
                    result = self._ensure_correct_answer_option(result, back)
                    if provider != primary_provider:
                        logger.info(f"AI-Hints: Fallback successful using provider: {provider}")
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
        custom_provider_config = self.config.get("custom_providers") or {}
        if not isinstance(custom_provider_config, dict):
            custom_provider_config = {}
        custom_providers = list(custom_provider_config.keys())
        
        # Use custom priority list if configured, otherwise use default order
        priority = self.config.get("provider_priority")
        if not isinstance(priority, list):
            priority = PROVIDER_ORDER + custom_providers
            
        candidates = []

        if self._is_provider_ready(primary_provider, primary=True):
            candidates.append(primary_provider)
        else:
            logger.warning(
                f"AI-Hints: Primary provider '{primary_provider}' is not configured; checking fallbacks."
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

    def _call_provider(self, provider: str, system_prompt: str, prompt: str) -> Dict[str, List[str]]:
        custom_providers = self.config.get("custom_providers") or {}
        if not isinstance(custom_providers, dict):
            custom_providers = {}
        if provider == "anthropic":
            return self._call_anthropic(system_prompt, prompt)
        elif provider == "gemini":
            return self._call_gemini(system_prompt, prompt)
        elif provider in custom_providers:
            return self._call_custom_provider(provider, system_prompt, prompt)
        else:
            return self._call_openai_compatible(provider, system_prompt, prompt)

    def _call_custom_provider(self, provider_name: str, system_prompt: str, prompt: str) -> Dict[str, List[str]]:
        custom_providers = self.config.get("custom_providers") or {}
        if not isinstance(custom_providers, dict):
            custom_providers = {}
        custom_cfg = custom_providers.get(provider_name, {})
        if not isinstance(custom_cfg, dict):
            custom_cfg = {}
        url = str(custom_cfg.get("url", "") or "").strip()
        api_key = str(custom_cfg.get("api_key", "") or "").strip()
        custom_headers = custom_cfg.get("headers", {})
        if not isinstance(custom_headers, dict):
            logger.warning(
                f"AI-Hints: Ignoring non-object custom headers for provider {provider_name}."
            )
            custom_headers = {}

        headers = self._json_headers(api_key)
        headers.update(custom_headers)

        models = self._models_for_provider(provider_name, custom_cfg.get("model", ""), custom_cfg.get("model_fallbacks", []))
        for model in models:
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
                    return parsed
                logger.warning(f"AI-Hints: Custom provider {provider_name} model '{model}' returned no parseable hints/options.")
            except urllib.error.HTTPError as e:
                logger.error(f"AI-Hints Error (Custom Provider {provider_name}, model {model}): {e} - {self._read_http_error(e)}")
            except Exception as e:
                logger.error(f"AI-Hints Error (Custom Provider {provider_name}, model {model}): {e}")
        return {"hints": [], "options": []}

    def _call_openai_compatible(self, provider: str, system_prompt: str, prompt: str) -> Dict[str, List[str]]:
        api_key = self._api_key_for(provider)
        models = self._models_for_provider(provider)
        
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
            api_key = str(local_cfg.get("api_key", "") or api_key).strip()
            models = self._models_for_provider(provider, local_cfg.get("model", "") or DEFAULT_MODELS["local"])
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
                logger.info(f"Calling OpenRouter with models array: {models}")
                result = self._post_json(url, data, headers)
                content = self._extract_content(result)
                parsed = self._parse_json_result(content)
                if parsed.get("hints") or parsed.get("options") or parsed.get("distractors") or parsed.get("correct_answer"):
                    return parsed
                logger.warning("AI-Hints: OpenRouter models array returned no parseable hints/options.")
            except urllib.error.HTTPError as e:
                logger.error(f"AI-Hints Error (OpenRouter models array): {e} - {self._read_http_error(e)}")
            except Exception as e:
                logger.error(f"AI-Hints Error (OpenRouter models array): {e}")
            # If the models array call fails, we fall back to the per-model loop below as a safety measure.

        for model in models:
            data = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
            }
            if provider in ["openai", "groq", "deepseek", "mistral", "openrouter", "together", "sambanova", "cerebras", "nvidia", "huggingface"]:
                data["response_format"] = {"type": "json_object"}

            try:
                self._log_model_attempt(provider, model, models)
                result = self._post_json(url, data, headers)
                content = self._extract_content(result)
                parsed = self._parse_json_result(content)
                if parsed.get("hints") or parsed.get("options") or parsed.get("distractors") or parsed.get("correct_answer"):
                    return parsed
                logger.warning(f"AI-Hints: {provider} model '{model}' returned no parseable hints/options.")
            except urllib.error.HTTPError as e:
                logger.error(f"AI-Hints Error ({provider}, model {model}): {e} - {self._read_http_error(e)}")
            except Exception as e:
                logger.error(f"AI-Hints Error ({provider}, model {model}): {e}")
        return {"hints": [], "options": []}

    def _call_anthropic(self, system_prompt: str, prompt: str) -> Dict[str, List[str]]:
        api_key = self._api_key_for("anthropic")
        models = self._models_for_provider("anthropic")
        url = "https://api.anthropic.com/v1/messages"
        
        headers = self._json_headers()
        headers.update({
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01"
        })

        for model in models:
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
                    return parsed
                logger.warning(f"AI-Hints: Anthropic model '{model}' returned no parseable hints/options.")
            except urllib.error.HTTPError as e:
                logger.error(f"AI-Hints Error (Anthropic, model {model}): {e} - {self._read_http_error(e)}")
            except Exception as e:
                logger.error(f"AI-Hints Error (Anthropic, model {model}): {e}")
        return {"hints": [], "options": []}

    def _call_gemini(self, system_prompt: str, prompt: str) -> Dict[str, List[str]]:
        api_key = self._api_key_for("gemini")
        models = self._models_for_provider("gemini")

        headers = self._json_headers()
        headers["x-goog-api-key"] = api_key

        for model in models:
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

            # Enable explicit thinking for improved quality on Gemini 3 and 2.5 models
            lower_model = model.lower()
            if "gemini-3" in lower_model or "gemini-2.5" in lower_model or "gemini-flash-latest" in lower_model:
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
                    return parsed
                logger.warning(f"AI-Hints: Gemini model '{model}' returned no parseable hints/options.")
            except urllib.error.HTTPError as e:
                body = self._read_http_error(e)
                logger.error(f"AI-Hints Error (Gemini, model {model}): {e} - {body}")
                if self._should_skip_remaining_gemini_models(e, body):
                    logger.warning(
                        "AI-Hints: Gemini quota/rate limit hit; skipping remaining Gemini models and trying another provider."
                    )
                    break
            except Exception as e:
                logger.error(f"AI-Hints Error (Gemini, model {model}): {e}")
        return {"hints": [], "options": []}

    def _should_skip_remaining_gemini_models(self, error: urllib.error.HTTPError, body: str) -> bool:
        if getattr(error, "code", None) not in GEMINI_PROVIDER_EXHAUSTED_STATUSES:
            return False
        body_text = body or ""
        return (
            "RESOURCE_EXHAUSTED" in body_text
            or "Quota exceeded" in body_text
            or "rate-limits" in body_text
        )

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
        return str(self._api_keys().get(provider, "") or "").strip()

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

    def _models_for_provider(self, provider: str, primary_model: str = "", extra_fallbacks: List[str] = None) -> List[str]:
        configured = self.config.get("model_fallbacks") or {}
        if not isinstance(configured, dict):
            configured = {}
        configured_fallbacks = self._model_list(configured.get(provider, []))
        candidates = [
            primary_model or self._get_model(provider),
            *self._model_list(extra_fallbacks),
            *configured_fallbacks,
            *MODEL_FALLBACKS.get(provider, []),
        ]

        models = []
        seen = set()
        for candidate in candidates:
            model = self._normalize_model(provider, candidate)
            if not model or model in seen:
                continue
            seen.add(model)
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
            logger.info(f"AI-Hints: Trying fallback model for {provider}: {model}")
        else:
            logger.info(f"AI-Hints: Calling {provider} with model: {model}")

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
        api_key = self._api_key_for(provider)
        if not api_key and provider != "local":
            return []

        try:
            if provider == "openrouter":
                url = "https://openrouter.ai/api/v1/models"
                headers = self._json_headers(api_key)
                result = self._get_json(url, headers)
                return [m.get("id") for m in result.get("data", []) if m.get("id")]
            
            elif provider == "gemini":
                url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
                result = self._get_json(url, {})
                # Filter for models that support generateContent
                models = []
                for m in result.get("models", []):
                    name = m.get("name", "")
                    if "generateContent" in m.get("supportedGenerationMethods", []):
                        if name.startswith("models/"):
                            name = name[7:]
                        models.append(name)
                return models

            elif provider == "groq":
                url = "https://api.groq.com/openai/v1/models"
                headers = self._json_headers(api_key)
                result = self._get_json(url, headers)
                return [m.get("id") for m in result.get("data", []) if m.get("id")]

            elif provider == "local":
                local_cfg = self.config.get("local_endpoint") or {}
                base_url = str(local_cfg.get("base_url", "http://localhost:11434/v1")).rstrip("/")
                url = f"{base_url}/models"
                headers = self._json_headers(local_cfg.get("api_key", ""))
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
                    return [m.get("id") for m in result.get("data", []) if m.get("id")]

            # Custom providers
            custom_providers = self.config.get("custom_providers", {}) or {}
            if provider in custom_providers:
                custom_cfg = custom_providers[provider]
                url = str(custom_cfg.get("url", "") or "").strip()
                if url:
                    # Attempt to guess the models endpoint from base chat url
                    # If it ends in /chat/completions, try /models
                    models_url = url
                    if models_url.endswith("/chat/completions"):
                        models_url = models_url.replace("/chat/completions", "/models")
                    elif not models_url.endswith("/models"):
                        # If it's just a base URL like .../v1, append /models
                        models_url = models_url.rstrip("/") + "/models"
                    
                    api_key = str(custom_cfg.get("api_key", "") or "").strip()
                    custom_headers = custom_cfg.get("headers", {})
                    headers = self._json_headers(api_key)
                    if isinstance(custom_headers, dict):
                        headers.update(custom_headers)
                    
                    result = self._get_json(models_url, headers)
                    return [m.get("id") for m in result.get("data", []) if m.get("id")]

        except Exception as e:
            logger.error(f"AI-Hints: Failed to fetch models for {provider}: {e}")
        
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
