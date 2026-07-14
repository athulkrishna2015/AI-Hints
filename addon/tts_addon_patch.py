import importlib
import re
from bs4 import BeautifulSoup
from .logger import logger

# Regex to find an ai-hints div (JSON or container variant)
_AI_HINTS_DIV_RE = re.compile(
    r'<div\b[^>]*class=["\'][^"\']*(?:ai-hints-json|ai-hints-container)[^"\']*["\'][^>]*>.*?</div>',
    flags=re.DOTALL | re.IGNORECASE,
)


def _extract_ai_hints_div(html: str) -> str:
    """Return the first ai-hints div found in html, or empty string."""
    m = _AI_HINTS_DIV_RE.search(html)
    return m.group(0) if m else ""


def _strip_ai_hints_divs(html: str) -> str:
    """Remove all ai-hints divs from html."""
    return _AI_HINTS_DIV_RE.sub("", html)


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
                    text = _strip_ai_hints_divs(text)
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

    # 3. Patch bulk_to_notes.add_audio_to_card to preserve the ai-hints div on bulk TTS
    #
    # Root cause: the bulk TTS path fetches a note object at the START of the bulk job,
    # generates audio (which may take a while), then does:
    #   note[target_field] += "[sound:...]"
    #   col.update_note(note)
    # If something modified the note between the initial fetch and the save (e.g. our own
    # batch writer), or if the note object was stale/corrupted, the ai-hints div can be lost.
    #
    # Fix: before saving, re-read the CURRENT field value from the DB, extract any existing
    # hints div from it, strip it from the stale note value, append the sound tag, then
    # re-append the hints div — ensuring it is never lost.
    try:
        bulk_to_notes_mod = importlib.import_module("428593773.bulk_add_voices.bulk_to_notes")
        original_bulk_add_audio = bulk_to_notes_mod.add_audio_to_card

        def patched_bulk_add_audio_to_card(col, undo_entry_id, note, target_field, audio_path):
            """Wrapper that preserves the ai-hints div during bulk TTS note saves."""
            try:
                # Re-read the freshest version of this note from the DB so we have the
                # most up-to-date field value (in case our batch writer saved it after
                # the bulk job fetched the stale note object).
                fresh_note = col.get_note(note.id)
                fresh_field_val = fresh_note[target_field] if target_field in fresh_note.keys() else ""

                # Extract the hints div from the freshest copy.
                hints_div = _extract_ai_hints_div(fresh_field_val)
                logger.debug(
                    f"AI-Hints bulk TTS patch: note {note.id}, field '{target_field}', "
                    f"hints_div found: {bool(hints_div)}"
                )

                if hints_div:
                    # Strip any (possibly stale) hints div from the note object's field value
                    # so we don't duplicate it after re-appending below.
                    current_val = note[target_field] if target_field in note.keys() else ""
                    note[target_field] = _strip_ai_hints_divs(current_val)

                # Run the original save logic (appends [sound:...] and calls col.update_note)
                result = original_bulk_add_audio(col, undo_entry_id, note, target_field, audio_path)

                if hints_div:
                    # Re-read the note (original save may have committed it), re-attach hints div.
                    try:
                        saved_note = col.get_note(note.id)
                        saved_val = saved_note[target_field] if target_field in saved_note.keys() else ""
                        # Only re-append if the div is still missing (defensive).
                        if hints_div not in saved_val:
                            saved_note[target_field] = _strip_ai_hints_divs(saved_val) + hints_div
                            col.update_note(saved_note)
                            col.merge_undo_entries(undo_entry_id)
                            logger.debug(
                                f"AI-Hints bulk TTS patch: Re-attached hints div to note {note.id}."
                            )
                    except Exception as ex:
                        logger.error(f"AI-Hints: Failed to re-attach hints div after bulk TTS save: {ex}")

                return result

            except Exception as ex:
                logger.error(f"AI-Hints: patched_bulk_add_audio_to_card failed, falling back: {ex}")
                return original_bulk_add_audio(col, undo_entry_id, note, target_field, audio_path)

        bulk_to_notes_mod.add_audio_to_card = patched_bulk_add_audio_to_card
        logger.info("AI-Hints: Successfully patched PiperTTS bulk_to_notes.add_audio_to_card to preserve hints div.")
    except ModuleNotFoundError:
        logger.debug("AI-Hints: PiperTTS (428593773) bulk_to_notes module not found. Skipping patch.")
    except Exception as e:
        logger.error(f"AI-Hints: Failed to patch PiperTTS bulk_to_notes.add_audio_to_card: {e}")
