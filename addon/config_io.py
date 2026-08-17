def write_pretty_config(addon_package, config):
    """Write Anki config using the add-on manager."""
    from aqt import mw

    mw.addonManager.writeConfig(addon_package, config)


def write_pretty_config_preserve_keys(addon_package, config):
    """Write config, but never let empty api_keys wipe keys already on disk.

    The addon's save paths reconstruct `api_keys` from the live UI controls, so
    any key whose provider is not currently rendered (or that was loaded as
    empty) would otherwise be silently dropped. This merges the on-disk keys
    back in before writing.
    """
    from aqt import mw

    config = dict(config or {})
    incoming = config.get("api_keys") or {}
    if not isinstance(incoming, dict):
        incoming = {}
    try:
        current = mw.addonManager.getConfig(addon_package) or {}
    except Exception:
        current = {}
    current_keys = current.get("api_keys") or {}
    if not isinstance(current_keys, dict):
        current_keys = {}
    merged = {}
    for p, v in current_keys.items():
        merged[p] = v
    for p, v in incoming.items():
        if v:
            merged[p] = v
    config["api_keys"] = merged
    mw.addonManager.writeConfig(addon_package, config)
