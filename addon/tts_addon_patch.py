import importlib
import re
from bs4 import BeautifulSoup
from .logger import logger

def setup_tts_addon_patch():
    # 1. Patch remove_codes_from_text to strip AI hints before audio generation
    try:
        remove_codes_mod = importlib.import_module("428593773.bulk_add_voices.remove_codes")
        original_remove_codes_from_text = remove_codes_mod.remove_codes_from_text

        def patched_remove_codes_from_text(text):
            if text and '<' in text:
                try:
                    soup_clean = BeautifulSoup(text, "html.parser")
                    for div in soup_clean.find_all("div", class_=lambda c: c and ("ai-hints-json" in c or "ai-hints-container" in c)):
                        div.decompose()
                    text = str(soup_clean)
                except Exception as ex:
                    logger.debug(f"AI-Hints: bs4 decompose failed in TTS patch: {ex}")
                    # Regex fallback
                    text = re.sub(
                        r'<div\b[^>]*class=["\'][^"\']*(?:ai-hints-json|ai-hints-container)[^"\']*["\'][^>]*>.*?</div>',
                        '',
                        text,
                        flags=re.DOTALL | re.IGNORECASE
                    )
            return original_remove_codes_from_text(text)

        remove_codes_mod.remove_codes_from_text = patched_remove_codes_from_text
        logger.info("AI-Hints: Successfully patched PiperTTS remove_codes_from_text to strip AI data.")

        # Also patch subprocess_piper module namespace since it binds remove_codes_from_text at import time
        try:
            subprocess_piper_mod = importlib.import_module("428593773.subprocess_piper")
            subprocess_piper_mod.remove_codes_from_text = patched_remove_codes_from_text
            logger.info("AI-Hints: Successfully patched PiperTTS subprocess_piper.remove_codes_from_text.")
        except ModuleNotFoundError:
            pass
    except ModuleNotFoundError:
        logger.debug("AI-Hints: PiperTTS (428593773) remove_codes module not found. Skipping patch.")
    except Exception as e:
        logger.error(f"AI-Hints: Failed to patch PiperTTS remove_codes: {e}")

    # 2. Patch on_success to reload editor fields and prevent note content overwrites
    try:
        add_audio_mod = importlib.import_module("428593773.add_cards.add_audio_to_card")
        original_on_success = add_audio_mod.on_success

        def patched_on_success(webview, start_time):
            original_on_success(webview, start_time)
            try:
                if hasattr(webview, "kind") and hasattr(webview, "editor") and webview.editor:
                    from aqt.editor import EditorMode
                    if webview.editor.editorMode != EditorMode.ADD_CARDS:
                        webview.editor.loadNoteKeepingFocus()
            except Exception as ex:
                logger.error(f"AI-Hints: Failed to reload editor in patched on_success: {ex}")

        add_audio_mod.on_success = patched_on_success
        logger.info("AI-Hints: Successfully patched PiperTTS on_success to reload editor note.")
    except ModuleNotFoundError:
        logger.debug("AI-Hints: PiperTTS (428593773) add_audio_to_card module not found. Skipping patch.")
    except Exception as e:
        logger.error(f"AI-Hints: Failed to patch PiperTTS on_success: {e}")
