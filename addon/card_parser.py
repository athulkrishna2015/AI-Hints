import re
import json
import html
from typing import Any, List, Optional, Tuple, Dict
try:
    from .latex_fixer import fix_latex, normalize_math_text
except ImportError:
    # Fallback/debug info
    fix_latex = lambda x, **kwargs: x
    normalize_math_text = lambda x, **kwargs: x

class CardParser:

    def __init__(self, target_fields: List[str], note_type_fields: Dict[str, List[str]] = None, storage_mode: str = "json", mathjax_format: str = "delimiters", fix_latex: bool = False):
        self.target_fields = target_fields
        self.note_type_fields = note_type_fields or {}
        self.storage_mode = storage_mode
        self.mathjax_format = mathjax_format
        self.fix_latex = fix_latex
        self.container_class = "ai-hints-container"
        self.json_class = "ai-hints-json"

    def _fix_lazy_latex(self, text: str) -> str:
        """Repairs common AI math errors like missing backslashes or joined commands."""
        return fix_latex(text, output_format=self._latex_output_format(), fix_latex=self.fix_latex)

    def normalize_hint_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize generated hint text before storage or direct reviewer injection."""
        if not isinstance(data, dict):
            return {"hints": [], "options": []}

        # Check if it's a hints/options object
        if "hints" in data or "options" in data:
            normalized = {"hints": [], "options": []}
            for key in ("hints", "options"):
                values = data.get(key, [])
                if not isinstance(values, list):
                    values = [values]
                
                seen = set()
                for value in values:
                    text = str(value).strip()
                    # Strip hallucinations before any math normalization
                    text = self._strip_ai_hallucinations(text)
                    
                    text = self._normalize_math_text(text)
                    if self.mathjax_format == "tags":
                        text = self._convert_to_mathjax_tags(text)
                    
                    # Only dedupe options, hints can be similar
                    if key == "options":
                        # Normalize whitespace for comparison
                        cmp_text = " ".join(text.strip().casefold().split())
                        if cmp_text in seen:
                            continue
                        seen.add(cmp_text)
                    
                    normalized[key].append(text)
            return normalized
        
        # Handle keyed structure (e.g. c1, c2)
        normalized = {}
        for k, v in data.items():
            if isinstance(v, dict):
                normalized[k] = self.normalize_hint_data(v)
            else:
                normalized[k] = v
        return normalized

    def _strip_ai_hallucinations(self, text: str) -> str:
        if not text:
            return ""
        
        # 1. Strip trailing JSON or technical metadata hallucinations
        # We look for a trailing { ... } that contains technical keys.
        # We use \\* to match any number of backslashes before the quote (escaped JSON).
        text = re.sub(r'\s*\{[\s\S]*\\*"(?:hints|options|c\d+)\\*"\s*:[\s\S]*\}\s*$', '', text)
        
        # 2. Strip "Answer: " or "Option: " prefixes if AI included them
        # We ensure it's a prefix by using ^ and check for optional space after colon
        text = re.sub(r'^(?:Answer|Option|Hint|Choice|Distractor)\s*:\s*', '', text, flags=re.IGNORECASE)
        
        # 3. Strip surrounding quotes if the AI wrapped the entire string in them
        text = text.strip()
        if len(text) >= 2 and text[0] == text[-1] and text[0] in '"\'':
            text = text[1:-1]
            
        return text.strip()

    def _normalize_math_text(self, text: str) -> str:
        return normalize_math_text(text, output_format=self._latex_output_format(), fix_latex=self.fix_latex)

    def _latex_output_format(self) -> str:
        if str(self.mathjax_format).lower() in {"inline", "dollar", "dollars"}:
            return "dollars"
        return "anki"

    def _fix_latex_span(self, span: str) -> str:
        # Note: We keep this for internal calls, but it's now just a pass-through to the library.
        # However, many methods in CardParser were private helpers for this.
        # Since they are no longer used by the main logic (which moved to the library),
        # we can remove them.
        try:
            from .latex_fixer.latex_fixer import _fix_latex_span
        except ImportError:
            return span
        return _fix_latex_span(span)

    def _convert_to_mathjax_tags(self, text: str) -> str:
        r"""Converts standard LaTeX delimiters \( \) and \[ \] to Anki's <anki-mathjax> tags."""
        if not isinstance(text, str):
            return text

        text = normalize_math_text(text, output_format="anki", fix_latex=self.fix_latex)
        
        # Replace \( ... \) and \[ ... \] with <anki-mathjax> ... </anki-mathjax>
        text = re.sub(r'\\\((.*?)\\\)', r'<anki-mathjax>\1</anki-mathjax>', text, flags=re.DOTALL)
        text = re.sub(r'\\\[(.*?)\\\]', r'<anki-mathjax>\1</anki-mathjax>', text, flags=re.DOTALL)
        return text

    def get_note_content(self, note, card=None) -> Tuple[str, str]:
        """Extracts front and back content for AI context based on note type config."""
        model_name = note.model()["name"]
        field_names = self.note_type_fields.get(model_name)
        
        if field_names:
            # Use specific fields from config
            selected_fields = []
            for f_name in field_names:
                if f_name in note:
                    selected_fields.append((f_name, note[f_name]))
            if not selected_fields:
                return "", ""

            if "cloze" in model_name.lower():
                content = " ".join(value for _, value in selected_fields)
                back = ""
                content, back = self._focus_current_cloze(content, card)
                return self._clean_html(content), self._clean_html(back)

            front = selected_fields[0][1]
            back = "\n".join(value for _, value in selected_fields[1:])
            return self._clean_html(front), self._clean_html(back)
        
        # Fallback to default heuristic
        fields = note.items()
        fields = list(fields)
        front = ""
        back = ""
        
        if fields:
            front = fields[0][1]
            # If it's a Cloze card, we often don't need the other fields for generating options
            if "cloze" in model_name.lower():
                front, back = self._focus_current_cloze(front, card)
            else:
                back = "\n".join([v for k, v in fields[1:]])
        
        return self._clean_html(front), self._clean_html(back)

    def _clean_html(self, html_text: str) -> str:
        """Remove most HTML tags to reduce tokens and noise."""
        if not isinstance(html_text, str):
            html_text = str(html_text or "")
        # Remove scripts and styles
        html_text = re.sub(r"<(script|style).*?>.*?</\1>", "", html_text, flags=re.DOTALL | re.IGNORECASE)
        # Remove all other tags but keep content
        text = re.sub(r"<.*?>", " ", html_text)
        text = html.unescape(text)
        # Clean up whitespace
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _focus_current_cloze(self, text: str, card=None) -> Tuple[str, str]:
        """Mark the cloze deletion for the current card and extract all active answers."""
        cloze_number = self._card_ord(card)
        if cloze_number is None:
            return text, ""
        cloze_number += 1

        answers = []
        def replace_cloze(match):
            number = int(match.group(1))
            answer = match.group(2)
            hint = match.group(3) or ""
            if number != cloze_number:
                return answer

            answers.append(self._clean_html(answer))
            current = f"Current cloze deletion: {answer}"
            if hint:
                current += f" (existing hint: {hint})"
            return current

        focused_text = re.sub(r"\{\{c(\d+)::(.*?)(?:::([^{}]*?))?\}\}", replace_cloze, text, flags=re.DOTALL)
        return focused_text, ", ".join(answers)

    def update_note_with_hints(self, note, data: Dict[str, List[str]], toggles: Dict[str, bool] = None, card=None) -> bool:
        """Appends or replaces the AI hints block in the target field."""
        if not data or (not data.get("hints") and not data.get("options")):
            return False

        data = self.normalize_hint_data(data)

        # Determine the key for this card (e.g., 'c1' for cloze ord 0)
        card_key = None
        card_ord = self._card_ord(card)
        if card_ord is not None:
            card_key = f"c{card_ord + 1}"
        
        # Find target field
        field_name = self._find_target_field(note)
        if not field_name:
            # Fallback to last field if no target found
            note_keys = list(note.keys())
            if not note_keys:
                return False
            field_name = note_keys[-1]

        current_val = note[field_name]
        if not isinstance(current_val, str):
            current_val = str(current_val or "")
        
        if self.storage_mode == "json":
            new_val = self._update_json_block_in_field(current_val, data, card_key, toggles, card)
        else:
            content_block = self.build_hints_block(data, toggles, card)
            new_val = self._replace_or_append_block(current_val, content_block, card)

        note[field_name] = new_val
        return True

    def _update_json_block_in_field(self, current_val: str, new_data: Dict[str, List[str]], card_key: Optional[str], toggles: Dict[str, bool], card=None) -> str:
        pattern = re.compile(
            rf'<div\b[^>]*class=["\'][^"\']*{self.json_class}[^"\']*["\'][^>]*>(.*?)</div>',
            flags=re.DOTALL | re.IGNORECASE,
        )
        
        matches = list(pattern.finditer(current_val))
        
        # If no block exists, create a new one
        if not matches:
            payload = {card_key: new_data} if card_key else new_data
            content_block = self.build_hints_block(payload, toggles, card if not card_key else None)
            return current_val + "\n" + content_block

        # If a block exists, try to merge
        for match in matches:
            block_html = match.group(0)
            raw_payload = match.group(1)
            try:
                # Unescape and parse
                parsed = self._parse_json_payload(raw_payload)
                if not isinstance(parsed, dict):
                    parsed = {}
                
                # If it's a legacy top-level block and we now have a card_key, we convert it.
                if card_key:
                    if ("hints" in parsed or "options" in parsed) and not self._is_keyed_payload(parsed):
                        # Convert legacy to keyed
                        old_ord = self._data_attr(block_html, "data-ai-hints-card-ord")
                        old_key = f"c{int(old_ord)+1}" if old_ord and old_ord.isdigit() else "c1"
                        parsed = {
                            old_key: {
                                "hints": parsed.get("hints", []),
                                "options": parsed.get("options", []),
                            }
                        }
                    
                    parsed[card_key] = new_data
                else:
                    if isinstance(parsed, dict) and "hints" in parsed:
                         parsed.update(new_data)
                    else:
                        parsed = new_data
                
                # Build new block
                new_payload = html.escape(json.dumps(parsed), quote=False)
                new_attrs = self._build_attrs(toggles, card if not card_key else None)
                new_block = f'<div class="{self.json_class}" {new_attrs} style="display:none">{new_payload}</div>'
                
                return current_val[:match.start()] + new_block + current_val[match.end():]
            except Exception:
                continue

        # Fallback: append new
        payload = {card_key: new_data} if card_key else new_data
        content_block = self.build_hints_block(payload, toggles, card if not card_key else None)
        return current_val + "\n" + content_block

    def build_hints_block(self, data: Dict[str, List[str]], toggles: Dict[str, bool] = None, card=None) -> str:
        """Build the persisted/injected hints block for the configured storage mode."""
        data = self.normalize_hint_data(data)
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
        attrs = [f'data-ai-hints-addon-id="2119980872"']
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
            rf'<div\b[^>]*class=["\'][^"\']*(?:{self.json_class}|{self.container_class})[^"\']*["\'][^>]*>(.*?)</div>',
            flags=re.DOTALL | re.IGNORECASE,
        )
        for f_val in note.values():
            if not isinstance(f_val, str):
                continue
            for match in pattern.finditer(f_val):
                block = match.group(0)
                if self._block_matches_card(block, card) and self._json_block_has_data_for_card(block, match.group(1), card):
                    return block
        return None

    def clear_hints_from_note(self, note, card=None) -> bool:
        """Removes AI hints blocks matching the card from all fields."""
        pattern = re.compile(
            rf'<div\b[^>]*class=["\'][^"\']*(?:{self.json_class}|{self.container_class})[^"\']*["\'][^>]*>(.*?)</div>',
            flags=re.DOTALL | re.IGNORECASE,
        )
        cleared = False
        card_ord = self._card_ord(card)
        card_key = f"c{card_ord + 1}" if card_ord is not None else None

        for f_name in note.keys():
            current_val = note[f_name]
            if not isinstance(current_val, str):
                continue
            
            new_val = current_val
            field_cleared = False
            matches = list(pattern.finditer(current_val))
            # Work backwards to avoid offset issues
            for match in reversed(matches):
                block_html = match.group(0)
                
                if self.json_class in block_html and card_key:
                    # Try partial clear from keyed JSON
                    try:
                        raw_payload = match.group(1)
                        parsed = self._parse_json_payload(raw_payload)
                        if isinstance(parsed, dict) and card_key in parsed:
                            del parsed[card_key]
                            if parsed:
                                # Re-save updated JSON
                                new_payload = html.escape(json.dumps(parsed), quote=False)
                                new_block = block_html.replace(match.group(1), new_payload)
                                new_val = new_val[:match.start()] + new_block + new_val[match.end():]
                                field_cleared = True
                                continue
                            # Else if empty, fall through to full removal
                        elif isinstance(parsed, dict) and self._is_keyed_payload(parsed):
                            continue
                    except Exception:
                        pass

                if self._block_matches_card(block_html, card):
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
        if card is None:
            return not self._block_has_card_scope(block)

        card_id = self._card_attr(card, "id")
        card_ord = self._card_ord(card)

        block_id = self._data_attr(block, "data-ai-hints-card-id")
        if card_id and block_id:
            return card_id == block_id

        block_ord = self._data_attr(block, "data-ai-hints-card-ord")
        if card_ord is not None and block_ord:
            return str(card_ord) == block_ord

        # If block has no specific scope, it matches all cards of the note
        return not self._block_has_card_scope(block)

    def _block_has_card_scope(self, block: str) -> bool:
        return bool(
            self._data_attr(block, "data-ai-hints-card-id")
            or self._data_attr(block, "data-ai-hints-card-ord")
        )

    def _data_attr(self, block: str, name: str) -> str:
        match = re.search(rf'\b{re.escape(name)}\s*=\s*["\']([^"\']*)["\']', block, flags=re.IGNORECASE)
        return html.unescape(match.group(1)) if match else ""

    def _parse_json_payload(self, raw_payload: str) -> Any:
        return json.loads(html.unescape(raw_payload or ""))

    def _is_keyed_payload(self, payload: Dict[str, Any]) -> bool:
        if not isinstance(payload, dict):
            return False
        if "hints" in payload or "options" in payload:
            return False
        return any(re.fullmatch(r"c\d+", str(key)) for key in payload.keys())

    def _json_block_has_data_for_card(self, block: str, raw_payload: str, card=None) -> bool:
        if self.json_class not in block:
            return True

        card_ord = self._card_ord(card)
        if card_ord is None:
            return True

        try:
            parsed = self._parse_json_payload(raw_payload)
        except Exception:
            return True

        if isinstance(parsed, dict) and self._is_keyed_payload(parsed):
            return f"c{card_ord + 1}" in parsed
        return True

    def _build_html_block(self, data: Dict[str, List[str]], attrs: str = "") -> str:
        hints = data.get("hints", [])
        options = data.get("options", [])
        
        hints_html = ""
        if hints:
            items = "".join([f"<li>{self._safe_hint_item_html(h)}</li>" for h in hints])
            hints_html = f'<b>AI Hints:</b><br><ul class="ai-hints-hint-list">{items}</ul>'
            
        options_html = ""
        if options:
            items = "".join([f"<li>{self._safe_hint_item_html(o)}</li>" for o in options])
            options_html = f'<b>AI Options:</b><br><ul class="ai-hints-list">{items}</ul>'
            
        return f"""
<div class="{self.container_class}" {attrs}>
    <hr>
    {hints_html}
    {options_html}
</div>
"""

    def _safe_hint_item_html(self, value) -> str:
        escaped = html.escape(str(value), quote=True)
        escaped = re.sub(r'&lt;(anki-mathjax)&gt;', r'<\1>', escaped, flags=re.IGNORECASE)
        escaped = re.sub(r'&lt;/(anki-mathjax)&gt;', r'</\1>', escaped, flags=re.IGNORECASE)
        return escaped
