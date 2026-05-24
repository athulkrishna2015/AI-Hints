import re
import sys

def clean_ai_hints_from_text(text: str) -> str:
    if not isinstance(text, str):
        return text
    pattern = re.compile(
        r'(?:[\s\n\r]|<br\s*/?>|&nbsp;|<div>\s*</div>)*<div\b[^>]*class=["\'][^"\']*(?:ai-hints-json|ai-hints-container)[^"\']*["\'][^>]*>.*?</div>(?:[\s\n\r]|<br\s*/?>|&nbsp;|<div>\s*</div>)*',
        flags=re.DOTALL | re.IGNORECASE,
    )
    return re.sub(pattern, "", text).strip()

class CleanNoteProxy:
    def __init__(self, original_note):
        if isinstance(original_note, CleanNoteProxy):
            self._note = original_note._note
        else:
            self._note = original_note

    def __getattr__(self, name):
        return getattr(self._note, name)

    def __getitem__(self, key):
        val = self._note[key]
        if isinstance(val, str):
            return clean_ai_hints_from_text(val)
        return val

    def __setitem__(self, key, value):
        self._note[key] = value

    def __contains__(self, item):
        return item in self._note

    def __len__(self):
        return len(self._note)

    def keys(self):
        return self._note.keys()

    def values(self):
        return [clean_ai_hints_from_text(v) if isinstance(v, str) else v for v in self._note.values()]

    def items(self):
        return [(k, clean_ai_hints_from_text(v) if isinstance(v, str) else v) for k, v in self._note.items()]

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    @property
    def fields(self):
        return [clean_ai_hints_from_text(v) if isinstance(v, str) else v for v in self._note.fields]

class CleanCardProxy:
    def __init__(self, original_card):
        if isinstance(original_card, CleanCardProxy):
            self._card = original_card._card
        else:
            self._card = original_card

    def __getattr__(self, name):
        return getattr(self._card, name)

    def note(self):
        return CleanNoteProxy(self._card.note())

def patch_anki_terminator():
    try:
        from aqt import mw
    except ImportError:
        return

    resizable_web_view_class = None
    for name, module in list(sys.modules.items()):
        if "dock_web_view" in name:
            if hasattr(module, "ResizableWebView"):
                resizable_web_view_class = getattr(module, "ResizableWebView")
                break

    if not resizable_web_view_class:
        return

    # Check if already patched to avoid double patching
    if hasattr(resizable_web_view_class, "_ai_hints_patched"):
        return

    original_get_field_text = resizable_web_view_class.get_field_text
    original_load_and_interact = resizable_web_view_class.load_and_interact

    def patched_get_field_text(self, card=None):
        if card is None and mw.state == "review":
            card = mw.reviewer.card
        if card is not None:
            card = CleanCardProxy(card)
        
        # In original get_field_text:
        #   if card is None and mw.state == "review":
        #       card = mw.reviewer.card
        #   else:
        #       return
        # Since we resolved card, we pass None to original and mock mw.reviewer.card
        original_reviewer_card = mw.reviewer.card
        try:
            mw.reviewer.card = card
            return original_get_field_text(self, None)
        finally:
            mw.reviewer.card = original_reviewer_card

    def patched_load_and_interact(self, card=None, *args, **kwargs):
        if card is None and hasattr(self, "last_card") and self.last_card is not None:
            card = self.last_card
        if card is None and mw.state == "review":
            card = mw.reviewer.card

        if card is not None:
            card = CleanCardProxy(card)
        return original_load_and_interact(self, card, *args, **kwargs)

    resizable_web_view_class.get_field_text = patched_get_field_text
    resizable_web_view_class.load_and_interact = patched_load_and_interact
    resizable_web_view_class._ai_hints_patched = True

def setup_anki_terminator_patch():
    # Attempt patching immediately in case already loaded
    patch_anki_terminator()
    try:
        from aqt.qt import QTimer
        # Schedule another try in 1 second to make sure it's captured
        QTimer.singleShot(1000, patch_anki_terminator)
    except Exception:
        pass
