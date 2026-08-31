import json
import time
import os
import re
import html
import hashlib
import urllib.request
import urllib.error
import urllib.parse
import socket
import threading
from typing import List, Dict, Any, Tuple
from .logger import logger, state

try:
    from .latex_fixer import repair_latex_control_chars
except ImportError:
    repair_latex_control_chars = lambda x: x

try:
    from .json_repair import loads as repair_loads
except ImportError:
    repair_loads = json.loads

ADDON_PATH = os.path.dirname(__file__)

# Serialize blacklist.json writes (the blacklist is updated from many batch
# worker threads). Written atomically via a temp file + os.replace so a
# reader never sees a partial/empty file. Stored in the profile data dir
# (migrated from the addon folder on first use) so it survives addon updates.
_blacklist_lock = threading.Lock()

BLACKLIST_FILE = os.path.join(ADDON_PATH, "blacklist.json")
_blacklist_path_resolved = False


def _blacklist_path() -> str:
    """Resolve the blacklist file location once (profile data dir when running
    inside Anki; falls back to the addon folder elsewhere). Tests may point
    BLACKLIST_FILE at a temp path by setting _blacklist_path_resolved = True.
    """
    global _blacklist_path_resolved
    if not _blacklist_path_resolved:
        global BLACKLIST_FILE
        try:
            from .config_io import resolve_data_file

            BLACKLIST_FILE = resolve_data_file("blacklist.json")
        except Exception:
            pass
        _blacklist_path_resolved = True
    return BLACKLIST_FILE


def _write_blacklist_file(data):
    """Atomically write the blacklist payload to blacklist.json."""
    with _blacklist_lock:
        path = _blacklist_path()
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, path)

LOG_SYSTEM_PROMPT_CHARS = 120


def _extract_system_text(data: Any) -> str:
    """Pull the (constant) system prompt out of any of the provider payload shapes."""
    try:
        if not isinstance(data, dict):
            return ""
        msgs = data.get("messages")
        if isinstance(msgs, list):
            for m in msgs:
                if isinstance(m, dict) and m.get("role") == "system":
                    c = m.get("content")
                    return c if isinstance(c, str) else ""
        sys = data.get("system")
        if isinstance(sys, str):
            return sys
        si = data.get("system_instruction")
        if isinstance(si, dict):
            parts = si.get("parts")
            if isinstance(parts, list) and parts:
                p = parts[0]
                if isinstance(p, dict):
                    t = p.get("text")
                    return t if isinstance(t, str) else ""
        return ""
    except Exception:
        return ""

def _elide_system(data: Any, sys_hash: str) -> Any:
    """Return a copy of the request with the constant system prompt replaced by a marker,
    keeping the variable parts (user prompt, model, etc.) fully intact."""
    if not isinstance(data, dict):
        return data
    out = dict(data)
    marker = f"[SYSTEM LOGGED ONCE {sys_hash}]" if sys_hash else "[SYSTEM NONE]"
    msgs = out.get("messages")
    if isinstance(msgs, list):
        out["messages"] = []
        for m in msgs:
            if isinstance(m, dict) and m.get("role") == "system" and isinstance(m.get("content"), str):
                cm = dict(m)
                cm["content"] = marker
                out["messages"].append(cm)
            else:
                out["messages"].append(m)
    if isinstance(out.get("system"), str):
        out["system"] = marker
    if isinstance(out.get("system_instruction"), dict):
        out["system_instruction"] = {"parts": [{"text": marker}]}
    return out

# Set of system-prompt hashes already logged in full, so the constant prompt is
# only written to the log once per distinct value.
_LOGGED_SYSTEM_PROMPTS: set = set()

# Cache for the default config.json system prompt so generate_options() does
# not hit the disk on every single generation call.
_default_prompt_cache: Dict[str, Any] = {"mtime": None, "prompt": ""}


def _default_system_prompt() -> str:
    """Read the stock system prompt from the addon's config.json (cached by mtime)."""
    try:
        path = os.path.join(ADDON_PATH, "config.json")
        mtime = os.path.getmtime(path)
        if _default_prompt_cache["mtime"] != mtime:
            with open(path, "r", encoding="utf-8") as f:
                _default_prompt_cache["prompt"] = json.load(f).get("system_prompt", "")
            _default_prompt_cache["mtime"] = mtime
        return _default_prompt_cache["prompt"]
    except Exception:
        return ""

def _log_full_request(provider: str, model: str, data: Any) -> None:
    """Log the outbound request for debugging. The constant system prompt is logged in
    full only once (keyed by hash); subsequent requests log only the varying parts."""
    try:
        system_text = _extract_system_text(data)
        sys_hash = ""
        if system_text:
            sys_hash = hashlib.md5(system_text.encode("utf-8", errors="ignore")).hexdigest()[:12]
            if sys_hash not in _LOGGED_SYSTEM_PROMPTS:
                _LOGGED_SYSTEM_PROMPTS.add(sys_hash)
                logger.debug(f"AI-Hints {provider}/{model} SYSTEM PROMPT (logged once, hash {sys_hash}): {system_text}")
        elided = _elide_system(data, sys_hash)
        logger.debug(f"AI-Hints {provider}/{model} FULL REQUEST (system hash {sys_hash or 'none'}): {json.dumps(elided, ensure_ascii=False, default=str)}")
    except Exception as e:
        logger.debug(f"AI-Hints {provider}/{model} FULL REQUEST (serialize error: {e}): {data!r}")

def _log_full_response(provider: str, model: str, content: str) -> None:
    """Log the complete inbound response content for debugging."""
    logger.debug(f"AI-Hints {provider}/{model} FULL RESPONSE: {content}")

def _compact_request_data(data: Dict[str, Any], max_len: int = LOG_SYSTEM_PROMPT_CHARS) -> Dict[str, Any]:
    """Return a compact copy of a request payload for debug logging so the
    system prompt is omitted and user content truncated."""
    out = dict(data)

    messages = out.get("messages")
    if isinstance(messages, list):
        compact_messages = []
        for m in messages:
            if not isinstance(m, dict):
                compact_messages.append(m)
                continue
            role = m.get("role")
            if role == "system":
                # Omit system prompt completely from debug log
                continue
            cm = dict(m)
            content = cm.get("content")
            if isinstance(content, str) and len(content) > max_len:
                cm["content"] = f"[{len(content)} chars] {content[:max_len]}..."
            elif isinstance(content, list):
                cm["content"] = f"[{len(content)} parts]"
            compact_messages.append(cm)
        out["messages"] = compact_messages

    if "system" in out:
        out.pop("system", None)
    if "system_instruction" in out:
        out.pop("system_instruction", None)
    if isinstance(out.get("contents"), list):
        out["contents"] = "<truncated>"
    if isinstance(out.get("prompt"), str) and len(out["prompt"]) > max_len:
        out["prompt"] = f"[{len(out['prompt'])} chars]"

    return out

REQUEST_TIMEOUT_SECONDS = 10


def _load_addon_version() -> str:
    try:
        with open(os.path.join(ADDON_PATH, "VERSION"), "r", encoding="utf-8") as f:
            return f.read().strip() or "0"
    except Exception:
        return "0"


USER_AGENT = f"Anki-AI-Hints/{_load_addon_version()}"

GEMINI_PROVIDER_EXHAUSTED_STATUSES = {429}
MODEL_COOLDOWN_SECONDS = 3600  # 1 hour
FAILED_MODELS_CACHE: Dict[Tuple[str, str], float] = {}  # Legacy stub
FAILED_KEYS_CACHE: Dict[Tuple[str, str], float] = {}    # Legacy stub
FAILED_COMBOS_CACHE: Dict[Tuple[str, str, str], float] = {}  # (provider, model, api_key) -> expiry_timestamp
RATE_LIMIT_STREAK: Dict[Tuple[str, str, str], int] = {}    # (provider, model, api_key) -> consecutive_hits
_BLACKLIST_LOADED = False

# Global network state for background monitoring
_NETWORK_STATE = {"online": None, "last_check": 0}
_NETWORK_STATE_CALLBACKS = []

def register_network_state_callback(callback):
    """Register a callback invoked only when connectivity changes."""
    if callback not in _NETWORK_STATE_CALLBACKS:
        _NETWORK_STATE_CALLBACKS.append(callback)
    _ensure_network_monitor()

def _check_network_online() -> bool:
    """Internal helper to perform a quick connectivity check."""
    previous_state = _NETWORK_STATE["online"]
    sock = None
    try:
        # Check Cloudflare DNS (1.1.1.1) on port 53 (DNS)
        sock = socket.create_connection(("1.1.1.1", 53), timeout=1.5)
        _NETWORK_STATE["online"] = True
    except OSError:
        _NETWORK_STATE["online"] = False
    finally:
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
    _NETWORK_STATE["last_check"] = time.time()
    if previous_state is not None and previous_state != _NETWORK_STATE["online"]:
        logger.info(
            "AI-Hints: Network %s; notifying generation controller.",
            "restored" if _NETWORK_STATE["online"] else "went offline",
        )
        for callback in tuple(_NETWORK_STATE_CALLBACKS):
            try:
                callback(_NETWORK_STATE["online"])
            except Exception as e:
                logger.error(f"AI-Hints: Network state callback failed: {e}")
    return _NETWORK_STATE["online"]

def _start_network_monitor():
    """Starts a background thread to periodically update network status (once)."""
    global _monitor_thread
    if _monitor_thread is not None and _monitor_thread.is_alive():
        return

    def monitor():
        _sleep_event = threading.Event()
        while True:
            _check_network_online()
            _sleep_event.wait(30)

    _monitor_thread = threading.Thread(target=monitor, daemon=True)
    _monitor_thread.name = "AI-Hints-NetworkMonitor"
    _monitor_thread.start()


# Started lazily on first AIClient construction / callback registration
# instead of at import time, so merely importing this module (e.g. in tests)
# doesn't spawn a permanent polling thread.
_monitor_thread = None


def _ensure_network_monitor():
    try:
        _start_network_monitor()
    except Exception:
        pass

PROVIDER_ORDER = [
    "anthropic",
    "openai",
    "deepseek",
    "grok",
    "gemini",
    "openrouter",
    "huggingface",
    "groq",
    "sambanova",
    "nvidia",
    "mistral",
    "cerebras",
]

# No hardcoded model names of any kind: providers change their model lists
# frequently, so any pre-shipped active model, UI suggestion, fallback chain,
# or legacy remap only goes stale and produces 404s. The active model and
# fallback lists for built-in providers come only from Fetch Models (or are
# typed by the user) and are persisted in config["models"] /
# config["model_fallbacks"]. Custom providers always carry their own model.
# Stale legacy names simply pass through and are caught by the provider's own
# API deprecation flags and the "deprecated"/"legacy" substring checks.
DEFAULT_MODELS = {}

# Intentionally empty - choices come from config and per-API fetches.
MODEL_SUGGESTIONS = {}

# Intentionally empty - stale legacy remaps rotted faster than they helped.
LEGACY_MODEL_REPLACEMENTS = {}

# Intentionally empty - fallback chains come from config["model_fallbacks"].
MODEL_FALLBACKS = {}

# Default endpoint URLs for built-in providers, used when a built-in provider
# is edited through the CustomProviderDialog so fetch/test can work without
# the user manually entering the endpoint.
BUILTIN_PROVIDER_URLS = {
    "openai": "https://api.openai.com/v1/chat/completions",
    "deepseek": "https://api.deepseek.com/chat/completions",
    "groq": "https://api.groq.com/openai/v1/chat/completions",
    "nvidia": "https://integrate.api.nvidia.com/v1/chat/completions",
    "grok": "https://api.x.ai/v1/chat/completions",
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
    "mistral": "https://api.mistral.ai/v1/chat/completions",
    "huggingface": "https://router.huggingface.co/v1/chat/completions",
    "sambanova": "https://api.sambanova.ai/v1/chat/completions",
    "cerebras": "https://api.cerebras.ai/v1/chat/completions",
    "anthropic": "https://api.anthropic.com/v1/messages",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/models",
}

# Cache of models flagged as deprecated by the provider's own API response
# during the most recent fetch_models() call. Populated online per provider.
FETCHED_DEPRECATED_MODELS: Dict[str, set] = {}

_DEPRECATION_MARKER_KEYS = (
    "deprecation", "deprecated", "is_deprecated",
    "expires_at", "expiresAt", "expiration", "expirationTimestamp",
)


def _model_id(item):
    """Extract a model identifier from a list-models response entry.

    Most OpenAI-compatible providers use ``id``, but a few (e.g. aihubmix)
    use ``model_id`` or ``name``. Return an empty string if none are present.
    """
    if not isinstance(item, dict):
        return ""
    for key in ("id", "model_id", "model", "name"):
        val = item.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""



def _collect_deprecated_items(items):
    """Return the set of model IDs a provider API marked as deprecated.

    Handles the common schemas: openrouter ``deprecation``, azure/github-style
    ``expiration*``/``expiresAt`` fields, and generic ``deprecated`` flags.
    """
    deprecated = set()
    for m in items or []:
        if not isinstance(m, dict):
            continue
        mid = m.get("id")
        if not mid:
            continue
        for key in _DEPRECATION_MARKER_KEYS:
            if m.get(key):
                deprecated.add(mid)
                break
    return deprecated


class _LingerPool:
    """Keeps timed-out requests alive in background threads.

    When a fallback candidate hits a read timeout, instead of discarding it we
    re-dispatch the same provider/model with an extended timeout on a daemon
    thread and immediately move on to the next candidate. If the slow request
    finishes while later candidates are still running — or after all of them
    failed — its result is claimed, preferring the highest-priority (earliest)
    candidate that produced one.
    """

    POLL_INTERVAL = 0.5

    def __init__(self, base_config: Dict[str, Any], linger_timeout: int, system_prompt: str, prompt: str):
        self._lock = threading.Lock()
        self._results = []          # [{"order": int, "provider": p, "model": m, "result": dict}]
        self._cancelled = False
        self._threads = []
        self._pending = set()       # orders of spawned-but-unresolved attempts
        self._base_config = dict(base_config or {})
        self._linger_timeout = linger_timeout
        self._system_prompt = system_prompt
        self._prompt = prompt

    def spawn(self, order: int, provider: str, override_model: str = ""):
        cfg = dict(self._base_config)
        # Long-deadline retry for both the review and pregen paths; per-model /
        # per-provider timeout overrides are neutralized so they cannot cut the
        # lingering attempt short.
        cfg["request_timeout"] = self._linger_timeout
        cfg["pregen_request_timeout"] = self._linger_timeout
        cfg["model_timeouts"] = {}
        cfg["provider_timeouts"] = {}
        pool = self

        def _run():
            try:
                client = AIClient(cfg)
                res = client._call_provider(provider, pool._system_prompt, pool._prompt, override_model=override_model)
                if isinstance(res, dict) and (res.get("hints") or res.get("options") or res.get("distractors") or res.get("correct_answer")):
                    with pool._lock:
                        if not pool._cancelled:
                            pool._results.append({"order": order, "provider": provider, "model": override_model, "result": res})
                    logger.info(f"AI-Hints Linger: late result arrived from {provider}/{override_model} (candidate #{order + 1}).")
                else:
                    logger.info(f"AI-Hints Linger: {provider}/{override_model} finished late with no usable content.")
            except Exception as e:
                logger.info(f"AI-Hints Linger: late attempt {provider}/{override_model} failed: {e}")
            finally:
                with pool._lock:
                    pool._pending.discard(order)

        t = threading.Thread(target=_run, name=f"ai-hints-linger-{provider}-{override_model}", daemon=True)
        with self._lock:
            if self._cancelled:
                return
            self._threads.append(t)
            self._pending.add(order)
        t.start()

    def has_pending_before(self, max_order: int) -> bool:
        """True while an attempt from a HIGHER-priority (earlier) candidate is in flight."""
        with self._lock:
            return any(o < max_order for o in self._pending)

    def has_pending(self) -> bool:
        """True while ANY lingering attempt is still in flight."""
        with self._lock:
            return bool(self._pending)

    def _claim_best(self, max_order=None):
        with self._lock:
            if not self._results:
                return None
            candidates = [r for r in self._results if max_order is None or r["order"] < max_order]
            if not candidates:
                return None
            best = min(candidates, key=lambda r: r["order"])
            self._results.remove(best)
            return best

    def claim_ready(self, max_order=None):
        """Return the earliest ready lingering result (without waiting), if any."""
        return self._claim_best(max_order)

    def wait_for_any(self, max_order=None):
        """Block until a lingering request yields a result, or all give up.

        Bounded by the linger timeout itself plus slack; aborts early on
        emergency stop or when the network goes down. With ``max_order``,
        only attempts from higher-priority (earlier) candidates count.
        """
        start = time.monotonic()
        while True:
            best = self._claim_best(max_order)
            if best is not None:
                return best
            with self._lock:
                pending = {o for o in self._pending if max_order is None or o < max_order}
                cancelled = self._cancelled
            if cancelled or not pending or state.GLOBAL_STOP or _NETWORK_STATE.get("online") is False:
                return None
            if time.monotonic() - start > self._linger_timeout + 15:
                return None
            time.sleep(self.POLL_INTERVAL)

    def cancel(self):
        """Discard all pending results; in-flight threads finish harmlessly."""
        with self._lock:
            self._cancelled = True
            self._results.clear()


class AIClient:
    # (linger_pool, order) while an outer fallback loop is walking candidates;
    # inner per-provider model loops consult it to spawn lingering retries on
    # read timeouts that would otherwise be absorbed silently. None elsewhere.
    _active_linger = None

    def __init__(self, config: Dict[str, Any], is_pregen: bool = False, is_batch: bool = False):
        _ensure_network_monitor()
        self.config = config or {}
        self._key_names: Dict[Tuple[str, str], str] = {}
        self.is_pregen = is_pregen
        self.is_batch = is_batch
        self._request_provider = None
        self._request_model = None
        # Optional UI progress hook: called with "Lingering" when a fallback
        # walk blocks on a higher-priority lingering retry, and with None when
        # it stops. Callers that own a frontend (reviewer_hooks) set this.
        self.status_cb = None

    def _notify_status(self, status):
        cb = getattr(self, "status_cb", None)
        if callable(cb):
            try:
                cb(status)
            except Exception:
                pass

    @property
    def _linger_prefers_priority(self) -> bool:
        """Race policy for lingering retries vs later candidates' successes.

        "priority" (default): a still-running attempt from an earlier
        (higher-priority) candidate outranks a later candidate's fresh
        success — generation waits out its extended deadline.
        "first": first usable result wins, no waiting.
        """
        try:
            return str(self.config.get("linger_race_policy", "priority") or "priority").strip().lower() != "first"
        except Exception:
            return True

    @property
    def timeout(self) -> int:
        try:
            # Type-specific base budget: each flow gets its own generous
            # default (unattended flows more than foreground).
            if self.is_pregen:
                base = int(self.config.get("pregen_request_timeout", 120))
            elif self.is_batch:
                base = int(self.config.get("batch_request_timeout", 120))
            else:
                base = int(self.config.get("request_timeout", 60))

            # Custom per-model / per-provider timeouts are honored for EVERY
            # flow, but only as an EXTENSION: a value below the flow's base
            # never shortens it, so unattended budgets keep their headroom.
            best = base
            if self._request_provider and self._request_model:
                model_timeouts = self.config.get("model_timeouts", {}) or {}
                if isinstance(model_timeouts, dict):
                    provider_mt = model_timeouts.get(self._request_provider, {}) or {}
                    if isinstance(provider_mt, dict):
                        override = int(provider_mt.get(self._request_model, 0) or 0)
                        if override > best:
                            best = override
            provider_timeouts = self.config.get("provider_timeouts", {}) or {}
            if self._request_provider and isinstance(provider_timeouts, dict):
                override = int(provider_timeouts.get(self._request_provider, 0) or 0)
                if override > best:
                    best = override
            return best
        except Exception:
            return 120 if (self.is_pregen or self.is_batch) else 60

    def _linger_enabled(self) -> bool:
        """Linger-on-timeout: keep timed-out requests alive in the background."""
        try:
            return bool(self.config.get("linger_on_timeout", True))
        except Exception:
            return True

    def _linger_timeout(self) -> int:
        """Extended deadline for background (lingering) retry attempts.

        Defaults to 3x the effective request timeout, clamped to
        [180, 900] seconds; overridable via `timeout_linger_seconds`.
        """
        try:
            configured = int(self.config.get("timeout_linger_seconds", 0) or 0)
            if configured > 0:
                return configured
        except Exception:
            pass
        try:
            base = self.timeout
        except Exception:
            base = 60
        return min(max(base * 3, 180), 900)

    def _is_host_unreachable_error(self, e: Exception) -> bool:
        import socket
        import urllib.error
        if isinstance(e, (ConnectionRefusedError, ConnectionResetError, ConnectionError)):
            return True
        if isinstance(e, urllib.error.URLError):
            if not isinstance(e, urllib.error.HTTPError):
                reason_str = str(e.reason).lower()
                if "name or service not known" in reason_str or "temporary failure in name resolution" in reason_str:
                    return True
                if "no route to host" in reason_str or "connection refused" in reason_str:
                    return True
        err_str = str(e).lower()
        if "name or service not known" in err_str or "no route to host" in err_str or "connection refused" in err_str:
            return True
        return False

    def _is_read_timeout_error(self, e: Exception) -> bool:
        import socket
        import urllib.error
        if isinstance(e, (socket.timeout, TimeoutError)):
            return True
        if isinstance(e, urllib.error.URLError):
            if isinstance(e, urllib.error.HTTPError):
                return e.code in (408, 504)
            if isinstance(e.reason, (socket.timeout, TimeoutError)):
                return True
            if hasattr(e.reason, "strerror") and "timed out" in str(e.reason.strerror).lower():
                return True
            if "timed out" in str(e.reason).lower() or "timeout" in str(e.reason).lower():
                return True
        err_str = str(e).lower()
        if "timed out" in err_str or "timeout" in err_str:
            return True
        return False

    def _is_network_or_timeout_error(self, e: Exception) -> bool:
        return self._is_host_unreachable_error(e) or self._is_read_timeout_error(e)

    def generate_options(self, front: str, back: str, override_provider: str = None, only_this_provider: bool = False, override_model: str = None) -> Dict[str, List[str]]:
        primary_provider = override_provider or self.config.get("ai_provider", "openai")
        # Always dynamically read the core prompt from the default config.json
        # so it gets updated automatically when the addon is upgraded (cached).
        default_prompt = _default_system_prompt()
            
        if not default_prompt:
            default_prompt = self.config.get("system_prompt", "")
            
        additional_instr = (self.config.get("additional_system_instructions", "") or "").strip()
        system_prompt = default_prompt.strip()
        if additional_instr:
            system_prompt = f"{system_prompt}\n\n**USER CUSTOM INSTRUCTIONS**\n{additional_instr}"
        count = self._options_count()

        # Master generation switch: which kinds of content the LLM should produce.
        # Applies to every generation path (manual, auto, pregen, batch).
        hints_enabled = bool(self.config.get("generate_hints_enabled", True))
        options_enabled = bool(self.config.get("generate_options_enabled", True))

        from .logger import log_context
        is_test = getattr(log_context, "source", None) == "model_test"
        if not (hints_enabled or options_enabled) and not is_test:
            logger.info("AI-Hints: Generation disabled (both hints and options are off). No API call made.")
            return {"hints": [], "options": []}

        if hints_enabled and options_enabled:
            mode_instructions = (
                f"- Generate exactly {count} total options (1 correct, {count-1} distractors) and exactly 3 conceptual hints.\n"
                "- If using 'distractors' key, provide only incorrect options. If 'options', include the correct answer.\n"
            )
        elif hints_enabled:
            mode_instructions = (
                "- Generate 3 conceptual hints ONLY. Do NOT generate any multiple-choice options, correct_answer, or distractors.\n"
                "- Return a JSON object containing ONLY the 'hints' key.\n"
            )
        else:
            mode_instructions = (
                f"- Generate exactly {count} total options (1 correct, {count-1} distractors) and NO hints.\n"
                "- Do NOT generate any hints. Return a JSON object WITHOUT a 'hints' key.\n"
                "- If using 'distractors' key, provide only incorrect options. If 'options', include the correct answer.\n"
            )
        
        # Add strict formatting every time; user-provided prompts often omit the exact count.
        system_prompt = (
            f"{system_prompt}\n\n" if system_prompt else ""
        ) + (
            "CRITICAL:\n"
            f"{mode_instructions}"
            "- Return ONLY strictly valid raw JSON. No markdown, no preambles.\n"
            "- Ensure all options match the correct answer's format, length, and style perfectly.\n"
            "- For multiple clozes with same ID, use semicolon-separated values (e.g., 'val1 ; val2').\n"
            f"{self._multi_formula_rule()}"
            "- For legal/case flashcards, do NOT invent synthetic facts or modify names/dates in the correct answer's text to make distractors; use outcomes of other actual, real-world cases/judgments.\n"
        )
        prompt = f"Front: {front}\nBack / correct answer: {back}" if back else f"Content: {front}"

        # Check if we should use the advanced global priority list
        global_priority = self.config.get("global_model_priority", [])
        use_global = self.config.get("use_global_model_priority", False)
        network_failed_providers = set()
        
        if use_global and global_priority and not override_provider and not is_test:
            disabled_providers = self.config.get("disabled_providers") or []
            disabled_fallback_models = self.config.get("disabled_fallback_models") or {}
            
            last_exception = None
            linger_pool = _LingerPool(self.config, self._linger_timeout(), system_prompt, prompt) if self._linger_enabled() else None
            for gi, (provider, model) in enumerate(global_priority):
                if state.GLOBAL_STOP:
                    logger.info(f"AI-Hints: Generation aborted via Emergency Stop signal (global loop).")
                    return {"hints": [], "options": []}

                # Do not walk the remaining fallback models after the network
                # has gone away.  A request already in flight may finish with
                # a timeout, but retrying every provider only creates noise and
                # delays the normal offline pause/resume flow.
                if _NETWORK_STATE["online"] is False:
                    logger.info("AI-Hints: Network unavailable; stopping global fallback attempts.")
                    return {"hints": [], "options": []}

                # A timed-out earlier candidate may have finished while we were
                # busy with later ones — prefer its result over starting yet
                # another request.
                if linger_pool:
                    early = linger_pool.claim_ready(max_order=gi)
                    if early:
                        self._notify_status(None)
                        logger.info(f"AI-Hints Linger: using late result from {early['provider']}/{early['model']} instead of continuing down the list.")
                        try:
                            return self._finalize_result(early["result"], back, hints_enabled, options_enabled, is_test)
                        except Exception:
                            pass
                
                # Skip if provider is disabled or has failed with network error
                if provider in disabled_providers or provider in network_failed_providers:
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
                    self._active_linger = (linger_pool, gi)
                    try:
                        result = self._call_provider(provider, system_prompt, prompt, override_model=model)
                    finally:
                        self._active_linger = None
                    if result.get("hints") or result.get("options") or result.get("distractors") or result.get("correct_answer"):
                        # Priority policy: a still-running attempt from an
                        # EARLIER (higher-priority, usually smarter) candidate
                        # outranks this success — give it its extended deadline.
                        # "first" policy: the fresh success wins immediately.
                        if linger_pool and self._linger_prefers_priority:
                            early = linger_pool.claim_ready(max_order=gi)
                            if not early and linger_pool.has_pending_before(gi):
                                self._notify_status("Lingering")
                                try:
                                    early = linger_pool.wait_for_any(max_order=gi)
                                finally:
                                    self._notify_status(None)
                            if early:
                                logger.info(
                                    f"AI-Hints Linger: higher-priority late result from "
                                    f"{early['provider']}/{early['model']} wins over {provider}/{model}."
                                )
                                try:
                                    return self._finalize_result(early["result"], back, hints_enabled, options_enabled, is_test)
                                except Exception:
                                    pass
                        result = self._finalize_result(result, back, hints_enabled, options_enabled, is_test)
                        logger.debug(f"AI-Hints: Successful generation using: {provider}/{model}")
                        return result
                except Exception as e:
                    last_exception = e
                    logger.error(f"Global fallback model {provider}/{model} failed: {e}")
                    if linger_pool and self._is_read_timeout_error(e):
                        # Keep this slow request alive in the background while
                        # the remaining candidates are tried.
                        linger_pool.spawn(gi, provider, model)
                        self._notify_status("Lingering")
                    if self._is_network_or_timeout_error(e):
                        network_failed_providers.add(provider)
                        if not _check_network_online():
                            logger.info("AI-Hints: Network unavailable; stopping global fallback attempts.")
                            return {"hints": [], "options": []}
                    continue
            
            # Rescue when every candidate failed AND/OR a lingering attempt from
            # a timed-out candidate is still alive. The pending check matters
            # for single-candidate flows (e.g. batch's only_this_provider): a
            # lone model timeout returns an empty dict WITHOUT raising, which
            # used to skip the wait entirely and waste the lingering retry.
            if linger_pool and (last_exception is not None or linger_pool.has_pending()):
                # Every candidate failed — give the lingering background
                # requests their extended deadline to produce something.
                self._notify_status("Lingering")
                try:
                    got = linger_pool.wait_for_any()
                finally:
                    self._notify_status(None)
                if got:
                    logger.info(f"AI-Hints Linger: all candidates failed; using late result from {got['provider']}/{got['model']}.")
                    try:
                        return self._finalize_result(got["result"], back, hints_enabled, options_enabled, is_test)
                    except Exception:
                        pass
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
        linger_pool = _LingerPool(self.config, self._linger_timeout(), system_prompt, prompt) if (self._linger_enabled() and not is_test) else None
        # Try providers in sequence
        for pi, provider in enumerate(all_potential):
            if state.GLOBAL_STOP:
                logger.info(f"AI-Hints: Generation aborted via Emergency Stop signal (provider loop).")
                return {"hints": [], "options": []}
            if _NETWORK_STATE["online"] is False:
                logger.info("AI-Hints: Network unavailable; stopping provider fallback attempts.")
                return {"hints": [], "options": []}
            if provider in network_failed_providers:
                continue

            # Prefer a timed-out earlier candidate that finished in the
            # background over starting the next request.
            if linger_pool:
                early = linger_pool.claim_ready(max_order=pi)
                if early:
                    self._notify_status(None)
                    logger.info(f"AI-Hints Linger: using late result from {early['provider']}/{early['model']} instead of continuing down the list.")
                    try:
                        return self._finalize_result(early["result"], back, hints_enabled, options_enabled, is_test)
                    except Exception:
                        pass

            try:
                self._active_linger = (linger_pool, pi)
                try:
                    result = self._call_provider(provider, system_prompt, prompt, override_model=override_model or "")
                finally:
                    self._active_linger = None
                if result.get("hints") or result.get("options") or result.get("distractors") or result.get("correct_answer"):
                    # Same priority policy as the global loop: let a still-running
                    # higher-priority lingering attempt win before settling.
                    if linger_pool and self._linger_prefers_priority:
                        early = linger_pool.claim_ready(max_order=pi)
                        if not early and linger_pool.has_pending_before(pi):
                            self._notify_status("Lingering")
                            try:
                                early = linger_pool.wait_for_any(max_order=pi)
                            finally:
                                self._notify_status(None)
                        if early:
                            logger.info(
                                f"AI-Hints Linger: higher-priority late result from "
                                f"{early['provider']}/{early['model']} wins over {provider}."
                            )
                            try:
                                return self._finalize_result(early["result"], back, hints_enabled, options_enabled, is_test)
                            except Exception:
                                pass
                    result = self._finalize_result(result, back, hints_enabled, options_enabled, is_test)
                    if provider != primary_provider:
                        logger.debug(f"AI-Hints: Fallback successful using provider: {provider}")
                    return result
            except Exception as e:
                last_exception = e
                logger.error(f"Provider {provider} failed: {e}")
                if linger_pool and self._is_read_timeout_error(e):
                    # Keep this slow request alive in the background while
                    # the remaining providers are tried.
                    linger_pool.spawn(pi, provider, override_model or "")
                    self._notify_status("Lingering")
                if self._is_network_or_timeout_error(e):
                    network_failed_providers.add(provider)
                    if not _check_network_online():
                        logger.info("AI-Hints: Network unavailable; stopping provider fallback attempts.")
                        return {"hints": [], "options": []}
                continue
        
        if linger_pool and (last_exception is not None or linger_pool.has_pending()):
            # Pending-only rescue matters for single-candidate flows (batch's
            # only_this_provider): a lone model timeout returns an empty dict
            # WITHOUT raising, which used to skip the wait entirely.
            self._notify_status("Lingering")
            try:
                got = linger_pool.wait_for_any()
            finally:
                self._notify_status(None)
            if got:
                logger.info(f"AI-Hints Linger: all candidates failed; using late result from {got['provider']}/{got['model']}.")
                try:
                    return self._finalize_result(got["result"], back, hints_enabled, options_enabled, is_test)
                except Exception:
                    pass
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
        local_providers = self.config.get("local_providers") or {}
        if not isinstance(local_providers, dict):
            local_providers = {}
        if provider in local_providers:
            local_cfg = local_providers[provider]
            if not isinstance(local_cfg, dict):
                return False
            url = str(local_cfg.get("url") or local_cfg.get("base_url") or "").strip()
            return bool(url and local_cfg.get("enabled", True))

        if provider == "local":
            if primary:
                return True
            return bool(self._local_provider_configs())

        custom_providers = self.config.get("custom_providers") or {}
        if not isinstance(custom_providers, dict):
            custom_providers = {}
        if provider in custom_providers:
            custom_cfg = custom_providers[provider]
            if not isinstance(custom_cfg, dict):
                return False
            url = str(custom_cfg.get("url", "") or "").strip()
            if not url:
                return False
            from .logger import log_context
            is_test = getattr(log_context, "source", None) == "model_test"
            # If in model_test mode, model will be passed as override_model
            if is_test:
                return True
            # A model may live in the custom entry itself, the top-level
            # "models" map, or "model_fallbacks" — any of these counts as ready.
            if str(custom_cfg.get("model", "") or "").strip():
                return True
            models_cfg = self.config.get("models") or {}
            if isinstance(models_cfg, dict) and str(models_cfg.get(provider, "") or "").strip():
                return True
            fallbacks_cfg = self.config.get("model_fallbacks") or {}
            fb = fallbacks_cfg.get(provider) if isinstance(fallbacks_cfg, dict) else None
            if isinstance(fb, list) and any(str(x).strip() for x in fb):
                return True
            if isinstance(fb, str) and fb.strip():
                return True
            # Fallback: attempt to fetch models from models_url / /models endpoint
            try:
                fetched = self.fetch_models(provider)
                if fetched:
                    return True
            except Exception:
                pass
            return False

        return bool(self._api_key_for(provider))

    def _local_provider_configs(self) -> List[Dict[str, Any]]:
        local_providers = self.config.get("local_providers") or {}
        if not isinstance(local_providers, dict):
            local_providers = {}
        override_name = str(self.config.get("local_provider_override", "") or "").strip()
        configs: List[Dict[str, Any]] = []
        for name, cfg in local_providers.items():
            if not isinstance(cfg, dict):
                continue
            if override_name and name != override_name:
                continue
            merged = dict(cfg)
            if "base_url" not in merged and merged.get("url"):
                merged["base_url"] = merged.get("url")
            merged.setdefault("name", name)
            merged.setdefault("enabled", True)
            configs.append(merged)

        legacy_local = self.config.get("local_endpoint") or {}
        if isinstance(legacy_local, dict) and (legacy_local.get("base_url") or legacy_local.get("url") or legacy_local.get("model")):
            merged = dict(legacy_local)
            if "base_url" not in merged and merged.get("url"):
                merged["base_url"] = merged.get("url")
            merged.setdefault("name", "local")
            merged.setdefault("enabled", True)
            if not any(cfg.get("name") == merged["name"] for cfg in configs):
                configs.insert(0, merged)

        return [cfg for cfg in configs if cfg.get("enabled", True)]

    def _call_provider(self, provider: str, system_prompt: str, prompt: str, override_model: str = "") -> Dict[str, List[str]]:
        previous_provider = self._request_provider
        self._request_provider = provider
        custom_providers = self.config.get("custom_providers") or {}
        if not isinstance(custom_providers, dict):
            custom_providers = {}
        custom_cfg = custom_providers.get(provider, {}) or {}
        custom_url = str(custom_cfg.get("url", "") or "").strip()
        try:
            if custom_url:
                return self._call_custom_provider(provider, system_prompt, prompt, override_model=override_model)
            elif provider == "anthropic":
                return self._call_anthropic(system_prompt, prompt, override_model=override_model)
            elif provider == "gemini":
                return self._call_gemini(system_prompt, prompt, override_model=override_model)
            else:
                return self._call_openai_compatible(provider, system_prompt, prompt, override_model=override_model)
        finally:
            self._request_provider = previous_provider

    def _call_custom_provider(self, provider_name: str, system_prompt: str, prompt: str, override_model: str = "") -> Dict[str, List[str]]:
        custom_providers = self.config.get("custom_providers") or {}
        if not isinstance(custom_providers, dict):
            custom_providers = {}
        custom_cfg = custom_providers.get(provider_name, {})
        if not isinstance(custom_cfg, dict):
            custom_cfg = {}
        url = str(custom_cfg.get("url", "") or "").strip()
        if url and not url.endswith("/chat/completions"):
            url = url.rstrip("/") + "/chat/completions"
        
        keys = self._api_keys_for_custom(provider_name, custom_cfg)
        if not keys:
            keys = [""]
            
        custom_headers = custom_cfg.get("headers", {})
        if not isinstance(custom_headers, dict):
            custom_headers = {}
        body_params = custom_cfg.get("body_params", {})
        if not isinstance(body_params, dict):
            body_params = {}

        models = [override_model] if override_model else self._custom_provider_models(provider_name, custom_cfg)

        timeouts_count = 0
        for model in models:
            self._request_model = model
            if state.GLOBAL_STOP:
                break

            from .logger import log_context
            is_test = getattr(log_context, "source", None) == "model_test"
            if is_test:
                available_keys = keys
            else:
                available_keys = [k for k in keys if not self._is_combo_failed(provider_name, model, k)]
                if not available_keys and override_model:
                    # Explicit single-model request (Alt+click override): every
                    # key combo for this model is on cooldown — retry them all
                    # anyway rather than silently returning nothing.
                    available_keys = list(keys)
            if not available_keys:
                continue

            model_timed_out = False
            for idx, api_key in enumerate(available_keys):
                if state.GLOBAL_STOP:
                    break

                headers = self._json_headers(api_key)
                headers.update(custom_headers)

                data = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ]
                }
                if body_params:
                    data.update(body_params)
                # Apply per-model thinking level (overrides body_params)
                thinking_levels = self.config.get("thinking_levels", {}) or {}
                provider_levels = thinking_levels.get(provider_name, {}) if isinstance(thinking_levels, dict) else {}
                if isinstance(provider_levels, dict):
                    think_val = provider_levels.get(model, "")
                    if think_val and think_val != "off":
                        data["think"] = think_val

                try:
                    logger.debug(f"AI-Hints Custom {provider_name}/{model} request: {json.dumps(_compact_request_data(data))}")
                    _log_full_request(provider_name, model, data)
                    self._log_model_attempt(provider_name, model, models)
                    result = self._post_json(url, data, headers)
                    content = self._extract_content(result)
                    logger.debug(f"AI-Hints Custom {provider_name}/{model} response: {content[:2000]}")
                    _log_full_response(provider_name, model, content)
                    parsed = self._parse_generation_result(result)
                    if parsed.get("hints") or parsed.get("options") or parsed.get("distractors") or parsed.get("correct_answer"):
                        self._on_combo_success(provider_name, model, api_key)
                        parsed["_provider"] = provider_name
                        parsed["_model"] = model
                        parsed["_generated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                        return parsed
                    logger.warning(f"AI-Hints: Custom provider {provider_name} model '{model}' returned no parseable hints/options.")
                    self._mark_combo_failed(provider_name, model, api_key)
                except urllib.error.HTTPError as e:
                    body = self._read_http_error(e)
                    logger.error(f"AI-Hints Error (Custom Provider {provider_name}, model {model}): {e} - {body}")
                    from .logger import log_context
                    if getattr(log_context, "source", None) == "model_test":
                        if idx == len(available_keys) - 1:
                            raise Exception(f"{e} - {body}")
                        else:
                            self._mark_combo_failed(provider_name, model, api_key)
                            continue

                    delay = self._extract_retry_delay(provider_name, model, api_key, e, body)
                    self._mark_combo_failed(provider_name, model, api_key, delay)
                    if e.code in (408, 504):
                        model_timed_out = True
                        break
                except Exception as e:
                    logger.error(f"AI-Hints Error (Custom Provider {provider_name}, model {model}): {e}")
                    if self._is_read_timeout_error(e):
                        # Slow ≠ broken: never blacklist on a pure read timeout
                        # (the linger-on-timeout path may still rescue it).
                        model_timed_out = True
                        break
                    self._mark_combo_failed(provider_name, model, api_key)
                    if self._is_host_unreachable_error(e):
                        raise e

            if model_timed_out:
                timeouts_count += 1
                hook = self._active_linger
                if hook is not None and hook[0] is not None:
                    hook[0].spawn(hook[1], provider_name, model)
                    self._notify_status("Lingering")
                if timeouts_count >= 2:
                    raise TimeoutError(f"Multiple read timeouts for provider {provider_name}")

        return {"hints": [], "options": []}

    def _call_openai_compatible(self, provider: str, system_prompt: str, prompt: str, override_model: str = "") -> Dict[str, List[str]]:
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
            base_url = local_cfg.get("base_url", local_cfg.get("url", "http://localhost:11434/v1"))
            models = [override_model] if override_model else self._models_for_provider(provider, local_cfg.get("model", "") or DEFAULT_MODELS.get("local", ""))
        elif provider == "mistral":
            base_url = "https://api.mistral.ai/v1"
        elif provider == "huggingface":
            base_url = "https://router.huggingface.co/v1"
        elif provider == "sambanova":
            base_url = "https://api.sambanova.ai/v1"
        elif provider == "cerebras":
            base_url = "https://api.cerebras.ai/v1"
        
        url = f"{base_url}/chat/completions"

        timeouts_count = 0
        local_providers = self.config.get("local_providers") or {}
        if not isinstance(local_providers, dict):
            local_providers = {}
        is_named_local = provider in local_providers

        if provider == "local" or is_named_local:
            if is_named_local:
                cfg = local_providers[provider]
                merged = dict(cfg)
                if "base_url" not in merged and merged.get("url"):
                    merged["base_url"] = merged.get("url")
                merged.setdefault("name", provider)
                merged.setdefault("enabled", True)
                local_configs = [merged]
            else:
                local_configs = self._local_provider_configs()
        else:
            local_configs = []

        for model in models:
            self._request_model = model
            if state.GLOBAL_STOP:
                break

            keys = self._available_api_keys(provider)
            if provider == "local" or is_named_local:
                keys = [""]
            elif not keys:
                continue

            from .logger import log_context
            is_test = getattr(log_context, "source", None) == "model_test"
            if is_test:
                available_keys = keys
            else:
                available_keys = [k for k in keys if not self._is_combo_failed(provider, model, k)]
                if not available_keys and override_model:
                    # Explicit single-model request (Alt+click override): every
                    # key combo for this model is on cooldown — retry them all
                    # anyway rather than silently returning nothing.
                    available_keys = list(keys)
            if not available_keys:
                continue

            model_timed_out = False
            for idx, api_key in enumerate(available_keys):
                if state.GLOBAL_STOP:
                    break

                if provider == "local" or is_named_local:
                    for local_cfg in (local_configs or [self.config.get("local_endpoint") or {}]):
                        if state.GLOBAL_STOP:
                            break
                        if not isinstance(local_cfg, dict):
                            continue
                        base_url = str(local_cfg.get("base_url", local_cfg.get("url", "http://localhost:11434/v1"))).rstrip("/")
                        local_model = str(local_cfg.get("model", "") or DEFAULT_MODELS.get("local", "")).strip()
                        local_models = [override_model] if override_model else self._models_for_provider(provider, local_model)
                        actual_key = str(local_cfg.get("api_key", "") or api_key).strip()
                        headers = self._json_headers(actual_key)
                        url = f"{base_url}/chat/completions"
                        for local_model_name in local_models:
                            if state.GLOBAL_STOP:
                                break
                            data = {
                                "model": local_model_name,
                                "messages": [
                                    {"role": "system", "content": system_prompt},
                                    {"role": "user", "content": prompt}
                                ],
                            }
                            if provider in ["openai", "groq", "deepseek", "mistral", "openrouter", "sambanova", "cerebras", "nvidia"]:
                                data["response_format"] = {"type": "json_object"}
                            try:
                                logger.debug(f"AI-Hints {provider}/{local_model_name} request: {json.dumps(_compact_request_data(data))}")
                                _log_full_request(provider, local_model_name, data)
                                self._log_model_attempt(provider, local_model_name, local_models)
                                result = self._post_json(url, data, headers)
                                content = self._extract_content(result)
                                logger.debug(f"AI-Hints {provider}/{local_model_name} response: {content[:2000]}")
                                _log_full_response(provider, local_model_name, content)
                                parsed = self._parse_json_result(content)
                                if self._result_is_corrupt(parsed):
                                    logger.warning(f"AI-Hints: discarding corrupt {provider} model '{local_model_name}' output containing U+FFFD replacement characters.")
                                if not self._result_is_corrupt(parsed) and (parsed.get("hints") or parsed.get("options") or parsed.get("distractors") or parsed.get("correct_answer")):
                                    self._on_combo_success(provider, local_model_name, api_key)
                                    parsed["_provider"] = provider
                                    parsed["_model"] = local_model_name
                                    parsed["_generated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                                    return parsed
                                self._mark_combo_failed(provider, local_model_name, api_key)
                            except urllib.error.HTTPError as e:
                                body = self._read_http_error(e)
                                logger.error(f"AI-Hints Error ({provider}, model {local_model_name}): {e} - {body}")
                                if getattr(log_context, "source", None) == "model_test":
                                    self._mark_combo_failed(provider, local_model_name, api_key)
                                    continue
                                delay = self._extract_retry_delay(provider, local_model_name, api_key, e, body)
                                self._mark_combo_failed(provider, local_model_name, api_key, delay)
                            except Exception as e:
                                logger.error(f"AI-Hints Error ({provider}, model {local_model_name}): {e}")
                                self._mark_combo_failed(provider, local_model_name, api_key)
                    continue
                else:
                    actual_key = api_key

                headers = self._json_headers(actual_key)
                if provider == "openrouter":
                    headers["HTTP-Referer"] = "https://github.com/athulkrishna2015/ai-hints"
                    headers["X-OpenRouter-Title"] = "Anki AI-Hints"
                    headers["X-OpenRouter-Categories"] = "ide-extension"

                data = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                }
                if provider in ["openai", "groq", "deepseek", "mistral", "openrouter", "sambanova", "cerebras", "nvidia"]:
                    data["response_format"] = {"type": "json_object"}

                try:
                    logger.debug(f"AI-Hints {provider}/{model} request: {json.dumps(_compact_request_data(data))}")
                    _log_full_request(provider, model, data)
                    self._log_model_attempt(provider, model, models)
                    result = self._post_json(url, data, headers)
                    content = self._extract_content(result)
                    logger.debug(f"AI-Hints {provider}/{model} response: {content[:2000]}")
                    _log_full_response(provider, model, content)
                    parsed = self._parse_generation_result(result)
                    if parsed.get("hints") or parsed.get("options") or parsed.get("distractors") or parsed.get("correct_answer"):
                        self._on_combo_success(provider, model, api_key)
                        parsed["_provider"] = provider
                        parsed["_model"] = model
                        parsed["_generated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                        return parsed
                    logger.warning(f"AI-Hints: {provider} model '{model}' returned no parseable hints/options.")
                    self._mark_combo_failed(provider, model, api_key)
                except urllib.error.HTTPError as e:
                    body = self._read_http_error(e)
                    logger.error(f"AI-Hints Error ({provider}, model {model}): {e} - {body}")
                    from .logger import log_context
                    if getattr(log_context, "source", None) == "model_test":
                        if idx == len(available_keys) - 1:
                            raise Exception(f"{e} - {body}")
                        else:
                            self._mark_combo_failed(provider, model, api_key)
                            continue

                    delay = self._extract_retry_delay(provider, model, api_key, e, body)
                    self._mark_combo_failed(provider, model, api_key, delay)
                    if e.code in (408, 504):
                        model_timed_out = True
                        break
                except Exception as e:
                    logger.error(f"AI-Hints Error ({provider}, model {model}): {e}")
                    if self._is_read_timeout_error(e):
                        # Slow ≠ broken: never blacklist on a pure read timeout
                        # (the linger-on-timeout path may still rescue it).
                        model_timed_out = True
                        break
                    self._mark_combo_failed(provider, model, api_key)
                    if self._is_host_unreachable_error(e):
                        raise e

            if model_timed_out:
                timeouts_count += 1
                hook = self._active_linger
                if hook is not None and hook[0] is not None:
                    hook[0].spawn(hook[1], provider, model)
                    self._notify_status("Lingering")
                if timeouts_count >= 2:
                    raise TimeoutError(f"Multiple read timeouts for provider {provider}")

        return {"hints": [], "options": []}

    def _call_anthropic(self, system_prompt: str, prompt: str, override_model: str = "") -> Dict[str, List[str]]:
        models = [override_model] if override_model else self._models_for_provider("anthropic")
        url = "https://api.anthropic.com/v1/messages"
        
        timeouts_count = 0
        for model in models:
            self._request_model = model
            if state.GLOBAL_STOP:
                break
                
            keys = self._available_api_keys("anthropic")
            if not keys:
                continue

            from .logger import log_context
            is_test = getattr(log_context, "source", None) == "model_test"
            if is_test:
                available_keys = keys
            else:
                available_keys = [k for k in keys if not self._is_combo_failed("anthropic", model, k)]
                if not available_keys and override_model:
                    # Explicit single-model request (Alt+click override): every
                    # key combo for this model is on cooldown — retry them all
                    # anyway rather than silently returning nothing.
                    available_keys = list(keys)
            if not available_keys:
                continue

            model_timed_out = False
            for idx, api_key in enumerate(available_keys):
                if state.GLOBAL_STOP:
                    break

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
                    self._log_model_attempt("anthropic", model, models)
                    _log_full_request("anthropic", model, data)
                    result = self._post_json(url, data, headers)
                    content = self._extract_content(result)
                    _log_full_response("anthropic", model, content)
                    parsed = self._parse_generation_result(result)
                    if parsed.get("hints") or parsed.get("options") or parsed.get("distractors") or parsed.get("correct_answer"):
                        self._on_combo_success("anthropic", model, api_key)
                        parsed["_provider"] = "anthropic"
                        parsed["_model"] = model
                        parsed["_generated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                        return parsed
                    logger.warning(f"AI-Hints: Anthropic model '{model}' returned no parseable hints/options.")
                    self._mark_combo_failed("anthropic", model, api_key)
                except urllib.error.HTTPError as e:
                    body = self._read_http_error(e)
                    logger.error(f"AI-Hints Error (Anthropic, model {model}): {e} - {body}")
                    from .logger import log_context
                    if getattr(log_context, "source", None) == "model_test":
                        if idx == len(available_keys) - 1:
                            raise Exception(f"{e} - {body}")
                        else:
                            self._mark_combo_failed("anthropic", model, api_key)
                            continue

                    delay = self._extract_retry_delay("anthropic", model, api_key, e, body)
                    self._mark_combo_failed("anthropic", model, api_key, delay)
                    if e.code in (408, 504):
                        model_timed_out = True
                        break
                except Exception as e:
                    logger.error(f"AI-Hints Error (Anthropic, model {model}): {e}")
                    if self._is_read_timeout_error(e):
                        # Slow ≠ broken: never blacklist on a pure read timeout
                        # (the linger-on-timeout path may still rescue it).
                        model_timed_out = True
                        break
                    self._mark_combo_failed("anthropic", model, api_key)
                    if self._is_host_unreachable_error(e):
                        raise e

            if model_timed_out:
                timeouts_count += 1
                hook = self._active_linger
                if hook is not None and hook[0] is not None:
                    hook[0].spawn(hook[1], "anthropic", model)
                    self._notify_status("Lingering")
                if timeouts_count >= 2:
                    raise TimeoutError("Multiple read timeouts for provider anthropic")

        return {"hints": [], "options": []}

    def _call_gemini(self, system_prompt: str, prompt: str, override_model: str = "") -> Dict[str, List[str]]:
        models = [override_model] if override_model else self._models_for_provider("gemini")

        timeouts_count = 0
        for model in models:
            self._request_model = model
            if state.GLOBAL_STOP:
                break

            keys = self._available_api_keys("gemini")
            if not keys:
                continue

            from .logger import log_context
            is_test = getattr(log_context, "source", None) == "model_test"
            if is_test:
                available_keys = keys
            else:
                available_keys = [k for k in keys if not self._is_combo_failed("gemini", model, k)]
                if not available_keys and override_model:
                    # Explicit single-model request (Alt+click override): every
                    # key combo for this model is on cooldown — retry them all
                    # anyway rather than silently returning nothing.
                    available_keys = list(keys)
            if not available_keys:
                continue

            model_timed_out = False
            for idx, api_key in enumerate(available_keys):
                if state.GLOBAL_STOP:
                    break

                headers = self._json_headers()
                headers["x-goog-api-key"] = api_key

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
                    _log_full_request("gemini", model, data)
                    result = self._post_json(url, data, headers)
                    content = self._extract_content(result)
                    _log_full_response("gemini", model, content)
                    parsed = self._parse_generation_result(result)
                    if parsed.get("hints") or parsed.get("options") or parsed.get("distractors") or parsed.get("correct_answer"):
                        self._on_combo_success("gemini", model, api_key)
                        parsed["_provider"] = "gemini"
                        parsed["_model"] = model
                        parsed["_generated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                        return parsed
                    logger.warning(f"AI-Hints: Gemini model '{model}' returned no parseable hints/options.")
                    self._mark_combo_failed("gemini", model, api_key)
                except urllib.error.HTTPError as e:
                    body = self._read_http_error(e)
                    logger.error(f"AI-Hints Error (Gemini, model {model}): {e} - {body}")
                    from .logger import log_context
                    if getattr(log_context, "source", None) == "model_test":
                        if idx == len(available_keys) - 1:
                            raise Exception(f"{e} - {body}")
                        else:
                            self._mark_combo_failed("gemini", model, api_key)
                            continue

                    delay = self._extract_retry_delay("gemini", model, api_key, e, body)
                    self._mark_combo_failed("gemini", model, api_key, delay)
                    if e.code in (408, 504):
                        model_timed_out = True
                        break
                except Exception as e:
                    logger.error(f"AI-Hints Error (Gemini, model {model}): {e}")
                    if self._is_read_timeout_error(e):
                        # Slow ≠ broken: never blacklist on a pure read timeout
                        # (the linger-on-timeout path may still rescue it).
                        model_timed_out = True
                        break
                    self._mark_combo_failed("gemini", model, api_key)
                    if self._is_host_unreachable_error(e):
                        raise e

            if model_timed_out:
                timeouts_count += 1
                hook = self._active_linger
                if hook is not None and hook[0] is not None:
                    hook[0].spawn(hook[1], "gemini", model)
                    self._notify_status("Lingering")
                if timeouts_count >= 2:
                    raise TimeoutError("Multiple read timeouts for provider gemini")

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
        
        available_keys = [k for k in keys if not self._is_combo_failed("gemini", model, k)]
        if not available_keys:
            available_keys = keys

        last_err = None
        for api_key in available_keys:
            headers = self._json_headers()
            headers["x-goog-api-key"] = api_key
            try:
                _log_full_request("gemini", f"batch-{model}", payload)
                response = self._post_json(url, payload, headers)
                _log_full_response("gemini", f"batch-{model}", json.dumps(response, ensure_ascii=False, default=str))
                self._on_combo_success("gemini", model, api_key)
                return response
            except urllib.error.HTTPError as e:
                err_body = e.read().decode("utf-8", errors="ignore")
                if "FAILED_PRECONDITION" in err_body:
                     raise Exception("🔒 Access Denied: Your Gemini API key appears to be on the FREE TIER.\n\nNative Batch Generation is a Paid-Only feature. Please link a billing method in Google AI Studio to enable it, OR switch to the 'Sequential Local Queue' mode in your Batch tab for free support.")
                if e.code in [401, 403, 429] or (e.code == 400 and ("API_KEY_INVALID" in err_body or "API key not valid" in err_body)):
                    self._mark_combo_failed("gemini", model, api_key)
                    last_err = Exception(f"Google API Error ({e.code}) with key {self._key_identifier('gemini', api_key)}: {err_body}")
                    continue
                raise Exception(f"Google API Error ({e.code}): {err_body}")
            except Exception as e:
                self._mark_combo_failed("gemini", model, api_key)
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
        
        models = self._models_for_provider("gemini")
        model = models[0] if models else DEFAULT_MODELS.get("gemini", "")
        
        available_keys = [k for k in keys if not self._is_combo_failed("gemini", model, k)]
        if not available_keys:
            available_keys = keys

        last_err = None
        for api_key in available_keys:
            headers = self._json_headers()
            headers["x-goog-api-key"] = api_key
            try:
                req = urllib.request.Request(url, headers=headers, method="GET")
                with urllib.request.urlopen(req, timeout=30) as response:
                    raw = response.read().decode("utf-8")
                    self._on_combo_success("gemini", model, api_key)
                    return json.loads(raw)
            except urllib.error.HTTPError as e:
                err_body = self._read_http_error(e)
                if e.code in [401, 403, 429] or (e.code == 400 and ("API_KEY_INVALID" in err_body or "API key not valid" in err_body)):
                    self._mark_combo_failed("gemini", model, api_key)
                    last_err = Exception(f"Google API Error ({e.code}) with key {self._key_identifier('gemini', api_key)}: {err_body}")
                    continue
                raise
            except Exception as e:
                self._mark_combo_failed("gemini", model, api_key)
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
            result["correct_answer"] = self._clean_ai_math_output(str(parsed["correct_answer"]))
        if "distractors" in parsed:
            result["distractors"] = self._normalize_string_list(parsed["distractors"])
        return result
    def _reasoning_texts(self, result: Any) -> List[str]:
        """Collect candidate JSON strings from a reasoning model's extra fields.

        Minimax / Cline BYOK and other reasoning gateways frequently return the
        actual answer in ``message.reasoning`` and/or ``message.reasoning_details``
        rather than in ``message.content``. This gathers those strings so callers
        can try parsing them when the primary content yields nothing.
        """
        try:
            if not isinstance(result, dict):
                return []
            # Same top-level `data` envelope unwrapping as _extract_content.
            if isinstance(result.get("data"), dict) and "choices" in result["data"]:
                result = result["data"]
            choices = result.get("choices") if isinstance(result, dict) else None
            if not choices:
                return []
            first = choices[0]
            message = first.get("message", {}) if isinstance(first, dict) else {}
            if not isinstance(message, dict):
                return []
            out: List[str] = []
            reasoning = message.get("reasoning")
            if isinstance(reasoning, str) and reasoning.strip():
                out.append(reasoning)
            details = message.get("reasoning_details")
            if isinstance(details, list):
                for part in details:
                    if isinstance(part, dict) and part.get("text"):
                        out.append(str(part["text"]))
            return out
        except Exception:
            return []

    @staticmethod
    def _result_is_corrupt(parsed: Dict[str, Any]) -> bool:
        """True if any generated text contains a U+FFFD replacement character.

        A valid LLM response never contains U+FFFD; a lone replacement char is
        the universal on-wire corruption marker (bad tokenizer / broken model
        output — e.g. some Ollama cloud models mixing scripts). Treating such
        generations as failures lets the fallback/retry loop pick a working
        model instead of silently committing garbage hints to cards.
        """
        if not isinstance(parsed, dict):
            return False
        for key in ("hints", "options", "distractors"):
            val = parsed.get(key)
            if isinstance(val, list):
                for item in val:
                    if isinstance(item, str) and "\ufffd" in item:
                        return True
            elif isinstance(val, str) and "\ufffd" in val:
                return True
        ca = parsed.get("correct_answer")
        if isinstance(ca, str) and "\ufffd" in ca:
            return True
        return False

    def _parse_generation_result(self, result: Any) -> Dict[str, List[str]]:
        """Parse a chat-completion result into hints/options.

        Prefers the standard ``message.content`` text, then falls back to any
        reasoning blocks (``message.reasoning`` / ``message.reasoning_details``)
        which reasoning models may use to carry the JSON. Returns the first
        parse that yields usable hints/options, or the (empty) content parse.
        """
        parsed = self._parse_json_result(self._extract_content(result))
        if self._result_is_corrupt(parsed):
            logger.warning("AI-Hints: discarding corrupt model output containing U+FFFD replacement characters; will retry with a fallback model.")
        elif parsed.get("hints") or parsed.get("options") or parsed.get("distractors") or parsed.get("correct_answer"):
            return parsed
        for text in self._reasoning_texts(result):
            candidate = self._parse_json_result(text)
            if self._result_is_corrupt(candidate):
                logger.warning("AI-Hints: discarding corrupt reasoning block containing U+FFFD replacement characters.")
            elif candidate.get("hints") or candidate.get("options") or candidate.get("distractors") or candidate.get("correct_answer"):
                return candidate
        # A corrupt primary parse is discarded; fall back to reasoning blocks
        # and, if none are clean/usable, return an empty result so callers treat
        # the generation as "no parseable hints/options" and retry another model.
        if self._result_is_corrupt(parsed):
            return {"hints": [], "options": []}
        return parsed
    def _finalize_result(self, result: Dict[str, Any], back: str, hints_enabled: bool, options_enabled: bool, is_test: bool = False) -> Dict[str, Any]:
        """Normalizes the LLM response and strips content per the master switch.

        Test calls (settings provider/model checks) ignore the master switch so
        users can still verify connectivity while generation is disabled.
        """
        if not isinstance(result, dict):
            return result
        if options_enabled or is_test:
            result = self._ensure_correct_answer_option(result, back)
        if is_test:
            return result
        if not hints_enabled:
            result.pop("hints", None)
        if not options_enabled:
            for k in ("options", "correct_answer", "distractors"):
                result.pop(k, None)
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

    def _multi_formula_rule(self) -> str:
        """Prompt rule: multiple distinct formulas in ONE option / correct_answer
        must be separated with a semicolon so they are never mashed together."""
        return ("- Multiple formulae in ONE option or correct_answer MUST be separated with ' ; ' (e.g. a general formula and its special case). "
                "NEVER merge them together with no separator or glue one formula onto the end of another. Use the same ' ; ' separator in the correct_answer and every option. "
                "GOOD: \"\\eta = 1 - \\frac{Q_C}{Q_H} ; \\eta_{\\text{Carnot}} = 1 - \\frac{T_C}{T_H}\"  BAD (forbidden): \"...Q_H}\\eta_{\\text{Carnot}} = 1 - ...\".\n")

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

            # Match a trailing "(name)" or "[name]" suffix with MATCHING bracket
            # pairs only — previously "(name]" was also accepted.
            paren_match = (
                re.search(r'\s*\(([^()]*)\)\s*$', entry) or
                re.search(r'\s*\[([^\[\]]*)\]\s*$', entry)
            )
            if paren_match:
                name = paren_match.group(1).strip()
                key = entry[:paren_match.start()].strip()
            elif ":" in entry:
                parts = entry.split(":", 1)
                name = parts[0].strip()
                key = parts[1].strip()
                # NOTE: intentionally no length heuristics here — short
                # "name:key" pairs (e.g. "primary:key1") are a supported
                # format covered by tests.
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
        # Simply return all keys; filtering is done per-model inside the calling loops
        return self._api_keys_for(provider)

    def _mark_combo_failed(self, provider: str, model: str, api_key: str, delay_seconds: float = None):
        if not api_key:
            api_key = ""
        # Settings/model checks are diagnostic requests, not real generation.
        # Never let a failed test poison the production cooldown/blacklist.
        from .logger import log_context
        if getattr(log_context, "source", None) == "model_test":
            logger.debug(f"AI-Hints: Skipping blacklist for model test {provider}/{model}.")
            return
        import sys
        # Only blacklist if we are actually online.
        if "unittest" not in sys.modules and not self._is_actually_online():
            logger.info(f"AI-Hints: Skipping blacklist for {provider}/{model} ({api_key}) because network appears offline.")
            return

        streak_key = (provider, model, api_key)
        if delay_seconds is None:
            # Apply streak-based cooldown for ALL failures to prevent repeated lag
            streak = RATE_LIMIT_STREAK.get(streak_key, 0) + 1
            RATE_LIMIT_STREAK[streak_key] = streak

            cooldown_sec = self._cooldown_seconds()
            delay_seconds = cooldown_sec * streak
        else:
            streak = RATE_LIMIT_STREAK.get(streak_key, 0) + 1
            RATE_LIMIT_STREAK[streak_key] = streak
            
        expiry = time.time() + delay_seconds
        FAILED_COMBOS_CACHE[streak_key] = expiry
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
            
        preview = api_key[-6:] if len(api_key) > 6 else api_key
        logger.info(f"AI-Hints: Blacklisted combo {provider}/{model} (Key: ...{preview}) for {time_str} due to failure (Streak: {streak}).")

    def _on_combo_success(self, provider: str, model: str, api_key: str):
        if not api_key:
            api_key = ""
        key = (provider, model, api_key)
        needs_save = False
        if key in RATE_LIMIT_STREAK:
            logger.debug(f"AI-Hints: Resetting failure streak for {provider}/{model} ({api_key}) after success.")
            del RATE_LIMIT_STREAK[key]
            needs_save = True
        
        # If it was blacklisted, remove it
        if key in FAILED_COMBOS_CACHE:
            del FAILED_COMBOS_CACHE[key]
            needs_save = True
            
        if needs_save:
            self._save_blacklist()

    def _is_combo_failed(self, provider: str, model: str, api_key: str) -> bool:
        if not api_key:
            api_key = ""
        global _BLACKLIST_LOADED
        if not _BLACKLIST_LOADED:
            self._load_blacklist()
            
        key = (provider, model, api_key)
        expiry = FAILED_COMBOS_CACHE.get(key)
        if expiry is None:
            return False
        
        if time.time() > expiry:
            # Cooldown expired, remove from cache
            try:
                del FAILED_COMBOS_CACHE[key]
                self._save_blacklist()
            except KeyError:
                pass
            return False
            
        return True

    def _is_model_failed(self, provider: str, model: str) -> bool:
        """Returns True if the model is failed for all keys under this provider."""
        custom_providers = self.config.get("custom_providers") or {}
        if provider in custom_providers:
            custom_cfg = custom_providers.get(provider, {})
            keys = self._api_keys_for_custom(provider, custom_cfg)
        else:
            keys = self._api_keys_for(provider)
            
        if not keys:
            keys = [""]
        for key in keys:
            if not self._is_combo_failed(provider, model, key):
                return False
        return True

    # Legacy compatibility stubs to prevent import/access crashes:
    def _mark_key_failed(self, provider: str, api_key: str, delay_seconds: float = None):
        pass

    def _on_key_success(self, provider: str, api_key: str):
        pass

    def _mark_model_failed(self, provider: str, model: str, delay_seconds: float = None):
        pass

    def _on_model_success(self, provider: str, model: str):
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

    def is_network_available(self) -> bool:
        """Public helper for callers that need a cheap offline gate."""
        return self._is_actually_online()

    def _cooldown_seconds(self) -> float:
        try:
            return float(self.config.get("model_cooldown_minutes", 10) or 10) * 60
        except (TypeError, ValueError):
            return 10 * 60

    def _save_blacklist(self):
        """Persists the FAILED_COMBOS_CACHE and RATE_LIMIT_STREAK to blacklist.json.

        The blacklist is updated extremely frequently during a batch run, so it
        must NOT live inside meta.json (the file holding api_keys, providers and
        the entire user config). A single bad write there would wipe the whole
        config — which is exactly the 2026-08-20 corruption. Keeping it in its
        own dedicated file both isolates the failure domain and takes it off the
        high-churn meta.json write path entirely.
        """
        try:
            # Convert tuple keys to strings for JSON
            expiries = {f"{p}|{m}|{k}": e for (p, m, k), e in FAILED_COMBOS_CACHE.items()}
            streaks = {f"{p}|{m}|{k}": s for (p, m, k), s in RATE_LIMIT_STREAK.items()}

            data = {
                "combos_expiries": expiries,
                "streaks": streaks,
                "version": 3,
            }
            _write_blacklist_file(data)
        except Exception as e:
            logger.error(f"AI-Hints: Failed to save blacklist: {e}")

    def _load_blacklist(self):
        """Loads FAILED_COMBOS_CACHE and RATE_LIMIT_STREAK from blacklist.json.

        On first run (or after upgrading from a build that stored the blacklist
        inside meta.json) the data is migrated out of meta.json when
        blacklist.json is absent, so existing cooldowns are preserved.
        """
        global _BLACKLIST_LOADED
        _BLACKLIST_LOADED = True
        data = None
        try:
            path = _blacklist_path()
            if os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
            else:
                # Migrate legacy meta.json storage into the dedicated file.
                from .config_io import read_meta_config
                legacy = (read_meta_config() or {}).get("model_blacklist_data")
                if isinstance(legacy, dict):
                    data = legacy
                    try:
                        _write_blacklist_file(data)
                    except Exception:
                        pass
        except Exception as e:
            logger.error(f"AI-Hints: Failed to load blacklist: {e}")
            return

        if not isinstance(data, dict):
            return

        try:
            now = time.time()
            FAILED_COMBOS_CACHE.clear()
            RATE_LIMIT_STREAK.clear()

            if data.get("version") == 3:
                expiries = data.get("combos_expiries", {})
                streaks = data.get("streaks", {})

                for key, expiry in expiries.items():
                    parts = key.split("|")
                    if len(parts) == 3 and expiry > now:
                        FAILED_COMBOS_CACHE[(parts[0], parts[1], parts[2])] = expiry

                for key, streak in streaks.items():
                    parts = key.split("|")
                    if len(parts) == 3:
                        RATE_LIMIT_STREAK[(parts[0], parts[1], parts[2])] = streak
        except Exception as e:
            logger.error(f"AI-Hints: Failed to parse blacklist: {e}")

    def _extract_retry_delay(self, provider: str, model: str, api_key: str, error: urllib.error.HTTPError, body: str) -> float:
        """
        Calculates cooldown delay.
        For 429 (rate limit), we respect any Retry-After header or use streak-based logic.

        NOTE: This only COMPUTES the delay — it must not increment
        RATE_LIMIT_STREAK, because _mark_combo_failed() (which always runs
        right after with this delay) performs the single authoritative
        increment. Incrementing in both places double-advanced the streak
        and made cooldowns escalate twice as fast as configured.
        """
        if getattr(error, "code", None) != 429:
            return None

        cooldown_sec = self._cooldown_seconds()
        key = (provider, model, api_key)
        streak = RATE_LIMIT_STREAK.get(key, 0) + 1

        delay = cooldown_sec * streak
        logger.info(f"AI-Hints: Rate limit (429) hit for {provider}/{model} (Key: ...{api_key[-6:] if len(api_key)>6 else api_key}). Streak: {streak}. New delay: {delay/60:.1f} minutes.")
        return delay

    def _enabled_fallback_models(self, provider: str) -> List[str]:
        """Ordered list of ENABLED (checked) fallback models for a provider, honoring
        the disable/disabled_fallback_models list. Used as the source of truth for
        custom providers so an auto-set/first-fetched model is never used over the
        models the user explicitly enabled."""
        fallbacks = self._model_list((self.config.get("model_fallbacks") or {}).get(provider, []))
        disabled = set(self._model_list((self.config.get("disabled_fallback_models") or {}).get(provider, [])))
        from .logger import log_context
        is_test = getattr(log_context, "source", None) == "model_test"
        seen = set()
        out = []
        for m in fallbacks:
            m = self._normalize_model(provider, m)
            if not m or m in seen or m in disabled:
                continue
            if not is_test and self._is_model_failed(provider, m):
                continue
            seen.add(m)
            out.append(m)
        return out

    def _custom_provider_models(self, provider: str, custom_cfg: Dict[str, Any]) -> List[str]:
        """Determine the model candidates for a custom provider. The first ENABLED
        (checked) fallback model is authoritative; the provider's saved model field is
        only used as a last resort when nothing is enabled."""
        enabled = self._enabled_fallback_models(provider)
        if enabled:
            return enabled
        return self._models_for_provider(provider, custom_cfg.get("model", ""), custom_cfg.get("model_fallbacks", []))

    def _provider_models(self, provider: str) -> List[str]:
        """Returns the ordered model candidates for a provider, using the correct
        resolution for custom providers (first enabled fallback) vs built-in ones."""
        custom_providers = self.config.get("custom_providers") or {}
        cp = custom_providers.get(provider)
        if provider in custom_providers:
            return self._custom_provider_models(provider, cp if isinstance(cp, dict) else {})
        return self._models_for_provider(provider)

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

    # Substrings that identify non-chat models (embeddings, OCR, moderation,
    # TTS/transcription, realtime audio, experimental "labs" models). These can
    # never answer a chat/completions prompt, so they should never be offered as
    # fallback candidates or tested as if they were chat models.
    _NON_CHAT_MODEL_HINTS = (
        "embed", "ocr", "moderation", "-tts", "tts-", "/tts",
        "transcribe", "realtime", "labs-", "/labs", "/stt", "-stt",
    )

    def _is_non_chat_model(self, model_id: str) -> bool:
        mid = (model_id or "").lower()
        return any(hint in mid for hint in self._NON_CHAT_MODEL_HINTS)

    def _chat_only_models(self, model_ids: List[str]) -> List[str]:
        out = []
        for m in model_ids:
            if m and not self._is_non_chat_model(m):
                out.append(m)
        return out

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
        local_providers = self.config.get("local_providers") or {}
        if not isinstance(local_providers, dict):
            local_providers = {}
        is_named_local = provider in local_providers

        if provider == "local" or is_named_local:
            if is_named_local:
                local_cfgs = [local_providers[provider]]
            else:
                local_cfgs = self._local_provider_configs()
                if not local_cfgs:
                    local_cfgs = [self.config.get("local_endpoint") or {}]
            last_err = None
            for local_cfg in local_cfgs:
                if not isinstance(local_cfg, dict):
                    continue
                try:
                    base_url = str(local_cfg.get("base_url", local_cfg.get("url", "http://localhost:11434/v1"))).rstrip("/")
                    if not base_url.startswith(("http://", "https://")):
                        continue
                    url = f"{base_url}/models"
                    headers = self._json_headers(str(local_cfg.get("api_key", "") or "").strip())
                    result = self._get_json(url, headers)
                    models = [m.get("id") for m in result.get("data", []) if m.get("id")]
                    if models:
                        return models
                except Exception as e:
                    last_err = e
            if last_err:
                raise last_err
            return []
        keys = self._available_api_keys(provider)
        custom_providers = self.config.get("custom_providers", {}) or {}
        if not isinstance(custom_providers, dict):
            custom_providers = {}
        custom_provider_match = None
        if provider in custom_providers:
            custom_provider_match = provider
        else:
            for cp_name in custom_providers:
                if isinstance(cp_name, str) and cp_name.lower() == provider.lower():
                    custom_provider_match = cp_name
                    break
        if custom_provider_match is not None:
            custom_keys = self._api_keys_for_custom(custom_provider_match, custom_providers[custom_provider_match])
            if custom_keys:
                keys = custom_keys
            elif not keys:
                keys = [""]
        if not keys:
            return []

        last_err = None
        for api_key in keys:
            try:
                # Check custom_providers first — applies to any provider
                custom_providers = self.config.get("custom_providers", {}) or {}
                if not isinstance(custom_providers, dict):
                    custom_providers = {}
                custom_cfg = custom_providers.get(provider) or {}
                if not custom_cfg:
                    for cp_name, cp_cfg in custom_providers.items():
                        if isinstance(cp_name, str) and cp_name.lower() == provider.lower() and isinstance(cp_cfg, dict):
                            custom_cfg = cp_cfg
                            break
                custom_url = str(custom_cfg.get("url", "") or "").strip()
                if custom_url:
                    models_url = str(custom_cfg.get("models_url", "") or "").strip()
                    if not models_url:
                        models_url = custom_url
                        if models_url.endswith("/chat/completions"):
                            models_url = models_url.replace("/chat/completions", "/models")
                        elif not models_url.endswith("/models"):
                            models_url = models_url.rstrip("/") + "/models"
                    if not models_url.startswith(("http://", "https://")):
                        continue
                    custom_headers = custom_cfg.get("headers", {})
                    headers = self._json_headers(api_key)
                    if isinstance(custom_headers, dict):
                        headers.update(custom_headers)
                    result = self._get_json(models_url, headers)
                    FETCHED_DEPRECATED_MODELS[provider] = _collect_deprecated_items(result.get("data", []))
                    return self._chat_only_models([_model_id(m) for m in result.get("data", []) if _model_id(m)])

                if provider == "openrouter":
                    url = "https://openrouter.ai/api/v1/models"
                    headers = self._json_headers(api_key)
                    result = self._get_json(url, headers)
                    FETCHED_DEPRECATED_MODELS[provider] = _collect_deprecated_items(result.get("data", []))
                    return self._chat_only_models([m.get("id") for m in result.get("data", []) if m.get("id")])

                elif provider == "gemini":
                    # Pass the key via header, never the URL query string —
                    # URLs end up in proxy/server access logs.
                    url = f"https://generativelanguage.googleapis.com/v1beta/models"
                    headers = {"x-goog-api-key": api_key}
                    result = self._get_json(url, headers)
                    models = []
                    deprecated = set()
                    for m in result.get("models", []):
                        name = m.get("name", "")
                        if "generateContent" in m.get("supportedGenerationMethods", []):
                            if name.startswith("models/"):
                                name = name[7:]
                            models.append(name)
                        else:
                            dep_name = name[7:] if name.startswith("models/") else name
                            if dep_name:
                                deprecated.add(dep_name)
                    FETCHED_DEPRECATED_MODELS[provider] = deprecated
                    return self._chat_only_models(models)

                elif provider == "groq":
                    url = "https://api.groq.com/openai/v1/models"
                    headers = self._json_headers(api_key)
                    result = self._get_json(url, headers)
                    return self._chat_only_models([m.get("id") for m in result.get("data", []) if m.get("id")])

                elif provider == "local":
                    local_cfg = self.config.get("local_endpoint") or {}
                    base_url = str(local_cfg.get("base_url", "http://localhost:11434/v1")).rstrip("/")
                    url = f"{base_url}/models"
                    headers = self._json_headers(local_cfg.get("api_key", ""))
                    result = self._get_json(url, headers)
                    return [m.get("id") for m in result.get("data", []) if m.get("id")]

                # Generic OpenAI-compatible providers
                openai_style = ["openai", "deepseek", "mistral", "nvidia", "sambanova", "cerebras", "grok"]
                if provider in openai_style:
                    urls = {
                        "openai": "https://api.openai.com/v1/models",
                        "deepseek": "https://api.deepseek.com/models",
                        "mistral": "https://api.mistral.ai/v1/models",
                        "nvidia": "https://integrate.api.nvidia.com/v1/models",
                        "sambanova": "https://api.sambanova.ai/v1/models",
                        "cerebras": "https://api.cerebras.ai/v1/models",
                        "grok": "https://api.x.ai/v1/models",
                    }
                    url = urls.get(provider)
                    if url:
                        headers = self._json_headers(api_key)
                        result = self._get_json(url, headers)
                        return self._chat_only_models([m.get("id") for m in result.get("data", []) if m.get("id")])

                elif provider == "huggingface":
                    return MODEL_SUGGESTIONS.get("huggingface", [])

            except Exception as e:
                logger.debug(f"AI-Hints: model fetch failed for {provider}: {e}")
                last_err = e
                continue
        if last_err:
            logger.error(f"AI-Hints: Failed to fetch models for {provider}: {last_err}")
        return []

    def _get_json(self, url: str, headers: Dict[str, str]) -> Dict[str, Any]:
        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def _post_json(self, url: str, data: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
        body = json.dumps(self._drop_none(data)).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def _drop_none(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {k: self._drop_none(v) for k, v in value.items() if v is not None}
        if isinstance(value, list):
            return [self._drop_none(v) for v in value]
        return value

    def _log_usage(self, result: Any) -> None:
        if not isinstance(result, dict):
            return
        usage = result.get("usage")
        if not isinstance(usage, dict) or not usage:
            return
        try:
            parts = []
            for k in ("input_tokens", "prompt_tokens", "output_tokens", "completion_tokens", "total_tokens"):
                v = usage.get(k)
                if v not in (None, 0):
                    parts.append(f"{k}:{v}")
            if not parts:
                return
            model = result.get("model", "")
            logger.info(f"AI-Hints usage{( ' ' + str(model)) if model else ''}: " + ", ".join(parts))
        except Exception:
            pass

    def _extract_content(self, result: Any) -> str:
        self._log_usage(result)
        if not isinstance(result, dict):
            return str(result)
        # Some gateways (e.g. the Cline BYOK API) wrap the chat completion in a
        # top-level `data` envelope: {"data": {"choices": [...]}, "success": true}.
        # Unwrap it so content/reasoning under data.choices is actually read.
        if isinstance(result.get("data"), dict) and "choices" in result["data"]:
            result = result["data"]

        choices = result.get("choices")
        if choices:
            first = choices[0]
            message = first.get("message", {}) if isinstance(first, dict) else {}
            content = message.get("content")
            if content not in (None, ""):
                return content if isinstance(content, str) else json.dumps(content)
            text = first.get("text") if isinstance(first, dict) else None
            if text not in (None, ""):
                return text
            # Reasoning models (e.g. Minimax / Cline BYOK gateway) frequently
            # leave `content` empty or blank and put the actual answer in
            # `message.reasoning` / `message.reasoning_details[*].text`. Falling
            # back here lets those responses be parsed instead of surfacing as
            # "returned no parseable hints/options".
            reasoning = message.get("reasoning")
            if isinstance(reasoning, str) and reasoning.strip():
                return reasoning
            details = message.get("reasoning_details")
            if isinstance(details, list):
                reasoning_texts = [
                    p.get("text", "") for p in details
                    if isinstance(p, dict) and p.get("text")
                ]
                if reasoning_texts:
                    return "\n".join(reasoning_texts)

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
        
        text = repair_latex_control_chars(text)
        
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
    config = {}
    try:
        from aqt import mw
        if mw is not None and mw.addonManager is not None:
            config = mw.addonManager.getConfig(__name__.split(".")[0]) or {}
    except Exception:
        config = {}
    client = AIClient(config)
    client._load_blacklist()

def save_blacklist():
    """Globally saves the blacklist from memory caches."""
    config = {}
    try:
        from aqt import mw
        if mw is not None and mw.addonManager is not None:
            config = mw.addonManager.getConfig(__name__.split(".")[0]) or {}
    except Exception:
        config = {}
    client = AIClient(config)
    client._save_blacklist()

def is_model_blacklisted(provider: str, model: str, config: Dict[str, Any] = None) -> bool:
    """True when every configured key combo for (provider, model) is cooling down.

    `config` should be the live addon config so the provider's actual API keys
    are checked; without it only the anonymous ("") key combo is visible.
    """
    try:
        global _BLACKLIST_LOADED
        if not _BLACKLIST_LOADED and not FAILED_COMBOS_CACHE:
            load_blacklist()
        client = AIClient(config)
        return client._is_model_failed(provider, model)
    except Exception:
        return False

def derive_active_provider(config: Any) -> str:
    """Derive the primary provider from config, honoring keyless providers.

    Some providers do not require an API key (e.g. 'local' endpoints and custom
    providers that only need a URL), so selection cannot rely on api_keys alone.
    Returns the first non-disabled provider in priority order that is usable:
    local, a custom provider with a URL, or a built-in with an API key.
    """
    if not isinstance(config, dict):
        config = {}
    disabled = set(config.get("disabled_providers") or [])
    api_keys = config.get("api_keys") or {}
    if not isinstance(api_keys, dict):
        api_keys = {}
    custom_providers = config.get("custom_providers") or {}
    if not isinstance(custom_providers, dict):
        custom_providers = {}
    priority = config.get("provider_priority")
    if not isinstance(priority, list):
        priority = PROVIDER_ORDER + list(custom_providers.keys())
    for p in priority:
        if p in disabled:
            continue
        if p == "local":
            # Local endpoints need no API key.
            return p
        if p in custom_providers:
            cp = custom_providers[p]
            if isinstance(cp, dict) and str(cp.get("url", "") or "").strip():
                return p
            continue
        if api_keys.get(p):
            return p
    return ""

def is_model_deprecated(provider: str, model: str) -> bool:
    """Best-effort detection of deprecated/retired model IDs.

    Checks, in order:
      1. Deprecation flags returned by the provider's own model API during the
         most recent fetch (OpenRouter, GitHub, Gemini, custom endpoints).
      2. Legacy replacement mappings and obvious name markers.
    """
    if not model:
        return False
    try:
        fetched = FETCHED_DEPRECATED_MODELS.get(provider)
        if fetched and model in fetched:
            return True
        if (provider, model) in LEGACY_MODEL_REPLACEMENTS:
            return True
        lower = str(model).strip().lower()
        if "deprecated" in lower or "legacy" in lower:
            return True
    except Exception:
        return False
    return False
