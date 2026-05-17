# -*- coding: utf-8 -*-

import os
from aqt import mw
from .logger import logger

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
