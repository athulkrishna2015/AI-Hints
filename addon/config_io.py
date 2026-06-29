def write_pretty_config(addon_package, config):
    """Write Anki config using the add-on manager."""
    from aqt import mw

    mw.addonManager.writeConfig(addon_package, config)
