import re
import json
import html
from typing import List, Optional, Tuple, Dict

class CardParser:
    def __init__(self, target_fields: List[str], note_type_fields: Dict[str, List[str]] = None, storage_mode: str = "json"):
        self.target_fields = target_fields
        self.note_type_fields = note_type_fields or {}
        self.storage_mode = storage_mode
        self.container_class = "ai-hints-container"
        self.json_class = "ai-hints-json"

    def get_note_content(self, note, card=None) -> Tuple[str, str]:
        """Extracts front and back content for AI context based on note type config."""
        model_name = note.model()["name"]
        field_names = self.note_type_fields.get(model_name)
        
        if field_names:
            # Use specific fields from config
            content_parts = []
            for f_name in field_names:
                if f_name in note:
                    content_parts.append(note[f_name])
            content = " ".join(content_parts)
            if "cloze" in model_name.lower():
                content = self._focus_current_cloze(content, card)
            return self._clean_html(content), ""
        
        # Fallback to default heuristic
        fields = note.items()
        fields = list(fields)
        front = ""
        back = ""
        
        if fields:
            front = fields[0][1]
            # If it's a Cloze card, we often don't need the other fields for generating options
            if "cloze" in model_name.lower():
                front = self._focus_current_cloze(front, card)
                back = ""
            else:
                back = "\n".join([v for k, v in fields[1:]])
        
        return self._clean_html(front), self._clean_html(back)

    def _clean_html(self, html: str) -> str:
        """Remove most HTML tags to reduce tokens and noise."""
        # Remove scripts and styles
        html = re.sub(r"<(script|style).*?>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
        # Remove all other tags but keep content
        text = re.sub(r"<.*?>", " ", html)
        # Clean up whitespace
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _focus_current_cloze(self, text: str, card=None) -> str:
        """Mark the cloze deletion for the current card so the AI targets only it."""
        cloze_number = self._card_ord(card)
        if cloze_number is None:
            return text
        cloze_number += 1

        def replace_cloze(match):
            number = int(match.group(1))
            answer = match.group(2)
            hint = match.group(3) or ""
            if number != cloze_number:
                return answer

            current = f"Current cloze deletion: {answer}"
            if hint:
                current += f" (existing hint: {hint})"
            return current

        return re.sub(r"\{\{c(\d+)::(.*?)(?:::([^{}]*?))?\}\}", replace_cloze, text, flags=re.DOTALL)

    def update_note_with_hints(self, note, data: Dict[str, List[str]], toggles: Dict[str, bool] = None, card=None) -> bool:
        """Appends or replaces the AI hints block in the target field."""
        if not data or (not data.get("hints") and not data.get("options")):
            return False

        content_block = self.build_hints_block(data, toggles, card)
        
        # Find target field
        field_name = self._find_target_field(note)
        if not field_name:
            # Fallback to last field if no target found
            field_name = list(note.keys())[-1]

        current_val = note[field_name]
        
        new_val = self._replace_or_append_block(current_val, content_block, card)

        note[field_name] = new_val
        return True

    def build_hints_block(self, data: Dict[str, List[str]], toggles: Dict[str, bool] = None, card=None) -> str:
        """Build the persisted/injected hints block for the configured storage mode."""
        attrs = self._build_attrs(toggles, card)
        if self.storage_mode == "json":
            payload = html.escape(json.dumps(data), quote=False)
            return f'<div class="{self.json_class}" {attrs} style="display:none">{payload}</div>'
        return self._build_html_block(data, attrs)

    def _find_target_field(self, note) -> Optional[str]:
        note_fields = note.keys()
        for target in self.target_fields:
            if target in note_fields:
                return target
        return None

    def _build_attrs(self, toggles: Dict[str, bool] = None, card=None) -> str:
        attrs = []
        if toggles:
            attrs.extend([
                f'data-show-hints="{str(toggles.get("show_hints_button", True)).lower()}"',
                f'data-show-options="{str(toggles.get("show_options_button", True)).lower()}"',
            ])

        card_id = self._card_attr(card, "id")
        card_ord = self._card_ord(card)
        if card_id:
            attrs.append(f'data-ai-hints-card-id="{html.escape(card_id, quote=True)}"')
        if card_ord is not None:
            attrs.append(f'data-ai-hints-card-ord="{card_ord}"')
        return " ".join(attrs)

    def _card_attr(self, card, attr: str) -> str:
        if card is None:
            return ""
        value = getattr(card, attr, "")
        if callable(value):
            return ""
        text = str(value).strip()
        if not text or text.startswith("<"):
            return ""
        return text

    def _card_ord(self, card) -> Optional[int]:
        if card is None:
            return None
        value = getattr(card, "ord", None)
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.strip().isdigit():
            return int(value.strip())
        return None

    def find_hints_block(self, note, card=None) -> Optional[str]:
        """Searches all fields of the note for an AI hints block matching the card."""
        pattern = re.compile(
            rf'<div\b[^>]*class=["\'][^"\']*(?:{self.json_class}|{self.container_class})[^"\']*["\'][^>]*>.*?</div>',
            flags=re.DOTALL | re.IGNORECASE,
        )
        for f_val in note.values():
            if not isinstance(f_val, str):
                continue
            for match in pattern.finditer(f_val):
                block = match.group(0)
                if self._block_matches_card(block, card):
                    return block
        return None

    def clear_hints_from_note(self, note, card=None) -> bool:
        """Removes AI hints blocks matching the card from all fields."""
        pattern = re.compile(
            rf'<div\b[^>]*class=["\'][^"\']*(?:{self.json_class}|{self.container_class})[^"\']*["\'][^>]*>.*?</div>',
            flags=re.DOTALL | re.IGNORECASE,
        )
        cleared = False
        for f_name in note.keys():
            current_val = note[f_name]
            if not isinstance(current_val, str):
                continue
            
            new_val = current_val
            field_cleared = False
            matches = list(pattern.finditer(current_val))
            # Work backwards to avoid offset issues
            for match in reversed(matches):
                if self._block_matches_card(match.group(0), card):
                    new_val = new_val[:match.start()] + new_val[match.end():]
                    field_cleared = True
            
            if field_cleared:
                note[f_name] = new_val
                cleared = True
        
        return cleared

    def _replace_or_append_block(self, current_val: str, content_block: str, card=None) -> str:
        pattern = re.compile(
            rf'<div\b[^>]*class=["\'][^"\']*(?:{self.json_class}|{self.container_class})[^"\']*["\'][^>]*>.*?</div>',
            flags=re.DOTALL | re.IGNORECASE,
        )
        matches = list(pattern.finditer(current_val))
        if not matches:
            return current_val + "\n" + content_block

        for match in matches:
            if self._block_matches_card(match.group(0), card):
                return current_val[:match.start()] + content_block + current_val[match.end():]

        for match in matches:
            if not self._block_has_card_scope(match.group(0)):
                return current_val[:match.start()] + content_block + current_val[match.end():]

        return current_val + "\n" + content_block

    def _block_matches_card(self, block: str, card=None) -> bool:
        card_id = self._card_attr(card, "id")
        card_ord = self._card_ord(card)

        block_id = self._data_attr(block, "data-ai-hints-card-id")
        if card_id and block_id:
            return card_id == block_id

        block_ord = self._data_attr(block, "data-ai-hints-card-ord")
        if card_ord is not None and block_ord:
            return str(card_ord) == block_ord

        return not card_id and card_ord is None and not self._block_has_card_scope(block)

    def _block_has_card_scope(self, block: str) -> bool:
        return bool(
            self._data_attr(block, "data-ai-hints-card-id")
            or self._data_attr(block, "data-ai-hints-card-ord")
        )

    def _data_attr(self, block: str, name: str) -> str:
        match = re.search(rf'{name}=["\']([^"\']*)["\']', block)
        return html.unescape(match.group(1)) if match else ""

    def _build_html_block(self, data: Dict[str, List[str]], attrs: str = "") -> str:
        hints = data.get("hints", [])
        options = data.get("options", [])
        
        hints_html = ""
        if hints:
            items = "".join([f"<li>{html.escape(str(h))}</li>" for h in hints])
            hints_html = f'<b>AI Hints:</b><br><ul class="ai-hints-hint-list">{items}</ul>'
            
        options_html = ""
        if options:
            items = "".join([f"<li>{html.escape(str(o))}</li>" for o in options])
            options_html = f'<b>AI Options:</b><br><ul class="ai-hints-list">{items}</ul>'
            
        return f"""
<div class="{self.container_class}" {attrs}>
    <hr>
    {hints_html}
    {options_html}
</div>
"""
