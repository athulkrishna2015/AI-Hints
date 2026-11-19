"""Pure helpers for per-model variant settings (no Qt / Anki imports)."""

from typing import Dict, List, Tuple


def known_model_pairs(config: Dict) -> List[Tuple[str, str]]:
    """Every (provider, model) pair known from the configured model lists.

    Fetched models are persisted in the per-provider fallback lists and in
    the global priority lists (enabled and disabled), so this is the full set
    of models the user has ever fetched — not just the ones with overrides.
    """
    pairs = set()

    models_cfg = config.get("models") or {}
    if isinstance(models_cfg, dict):
        for provider, model in models_cfg.items():
            if isinstance(model, str) and model:
                pairs.add((str(provider), model))

    for key in ("model_fallbacks", "disabled_fallback_models"):
        group = config.get(key) or {}
        if not isinstance(group, dict):
            continue
        for provider, models in group.items():
            if isinstance(models, (list, tuple)):
                pairs.update((str(provider), str(m)) for m in models if m)

    for key in ("global_model_priority", "disabled_global_model_priority"):
        group = config.get(key) or []
        if isinstance(group, list):
            for entry in group:
                if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                    pairs.add((str(entry[0]), str(entry[1])))
    return sorted(pairs)
