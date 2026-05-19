# -*- coding: utf-8 -*-

import os
import re
from aqt import mw
from .logger import logger
from .config_ui import ADDON_PACKAGE

def sync_mobile_script():
    """Copies web/template.js to the Anki media folder. Only writes if content changed."""
    try:
        addon_dir = os.path.dirname(__file__)
        src_path = os.path.join(addon_dir, "web", "template.js")
        
        if not os.path.exists(src_path):
            logger.error(f"AI-Hints Mobile Sync: Source script not found at {src_path}")
            return False

        if not mw.col:
            return False

        dest_name = "_ai_hints_template.js"
        dest_path = os.path.join(mw.col.media.dir(), dest_name)

        with open(src_path, "r", encoding="utf-8") as f:
            new_content = f.read()

        should_copy = True
        if os.path.exists(dest_path):
            with open(dest_path, "r", encoding="utf-8") as f:
                old_content = f.read()
            if old_content == new_content:
                should_copy = False

        if should_copy:
            with open(dest_path, "w", encoding="utf-8") as f:
                f.write(new_content)
            logger.info(f"AI-Hints: Mobile template script synced to media folder as '{dest_name}'.")
        
        return True

    except Exception as e:
        logger.error(f"AI-Hints: Failed to sync mobile script: {e}")
        return False

def _get_full_template_block(field_name: str, template_html: str, config_js: str, is_cloze: bool = False, is_front: bool = False) -> str:
    should_inject = False
    if field_name:
        if is_cloze and is_front:
            # Always inject hidden cloze:field_name on the Front side of Cloze cards
            # to bypass AnkiDroid's raw field cloze leakage protection.
            should_inject = True
        elif template_html:
            has_field_tag = (
                f"{{{{{field_name}}}}}" in template_html or
                f":{field_name}}}" in template_html or
                f"cloze:{field_name}" in template_html
            )
            if not has_field_tag:
                should_inject = True
        else:
            should_inject = True
                
    field_expr = f"cloze:{field_name}" if (is_cloze and is_front) else field_name
    field_tag = f'<div style="display:none;">{{{{{field_expr}}}}}</div>' if should_inject else ""
    return (
        "<!-- AI-HINTS-BEGIN -->\n"
        f"{field_tag}\n"
        "<ai-hints></ai-hints>\n"
        "<script>\n"
        f"{config_js}\n"
        "</script>\n"
        "<script src='_ai_hints_template.js'></script>\n"
        "<!-- AI-HINTS-END -->"
    )

def auto_update_mobile_setup():
    """Silently updates script file and all templates IF the user previously opted-in 
    via the 'One-Click Install' button."""
    config = mw.addonManager.getConfig(ADDON_PACKAGE) or {}
    if not config.get("mobile_setup_completed", False):
        return

    # 1. Update script file
    sync_mobile_script()

    # 2. Update templates
    use_emojis = config.get("mobile_use_emojis", False)
    show_extra = config.get("mobile_show_extra_buttons", False)
    shortcuts = config.get("shortcuts", {})
    import json
    shortcuts_json = json.dumps(shortcuts)
    
    config_js = (
        "window.aiHintsMobileConfig = { "
        f"useEmojis: {'true' if use_emojis else 'false'}, "
        f"showExtraButtons: {'true' if show_extra else 'false'}, "
        f"shortcuts: {shortcuts_json} "
        "};"
    )
    
    pattern = r"<!-- AI-HINTS-BEGIN -->.*?<!-- AI-HINTS-END -->"
    
    try:
        updated_count = 0
        target_fields = config.get("target_fields", [])
        default_field = target_fields[0] if target_fields else "AI Hints"
        note_type_fields = config.get("note_type_fields", {})

        for model in mw.col.models.all():
            model_changed = False
            
            # Determine target field for this model (first matching target_field)
            model_fields = [f['name'] for f in model['flds']]
            field_name = None
            for tf in target_fields:
                if tf in model_fields:
                    field_name = tf
                    break
            if not field_name:
                field_name = model_fields[-1] if model_fields else default_field

            is_cloze = (model.get('type') == 1)
            for tmpl in model['tmpls']:
                for side in ['qfmt', 'afmt']:
                    old_html = tmpl[side]
                    # ONLY update if markers already exist
                    if "<!-- AI-HINTS-BEGIN -->" in old_html:
                        clean_html = re.sub(pattern, "", old_html, flags=re.DOTALL)
                        new_block = _get_full_template_block(
                            field_name, clean_html, config_js, is_cloze=is_cloze, is_front=(side == 'qfmt')
                        )
                        new_html = re.sub(pattern, new_block, old_html, flags=re.DOTALL)
                        if new_html != old_html:
                            tmpl[side] = new_html
                            model_changed = True
            
            if model_changed:
                mw.col.models.save(model)
                updated_count += 1
        
        if updated_count > 0:
            logger.info(f"AI-Hints: Automatically updated {updated_count} note types to match latest configuration.")

    except Exception as e:
        logger.error(f"AI-Hints: Error during automatic template update: {e}")
