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

    def __init__(self, storage_mode: str = "json", mathjax_format: str = "delimiters", fix_latex: bool = False, **kwargs):
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

        # Handle new format with separate correct_answer and distractors.
        # We keep correct_answer so it survives into JSON storage; it is NOT
        # rendered in the UI (the frontend only reads "hints" and "options").
        correct_answer_raw = None
        if "correct_answer" in data and "distractors" in data:
            ans = data.get("correct_answer", "")
            dist = data.get("distractors", [])
            if not isinstance(dist, list):
                dist = [dist]
            data["options"] = [ans] + dist
            correct_answer_raw = ans  # remember before merging

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
                        if not text:
                            continue
                        # Normalize whitespace for comparison
                        cmp_text = " ".join(text.strip().casefold().split())
                        if cmp_text in seen:
                            continue
                        seen.add(cmp_text)
                    
                    normalized[key].append(text)

            # Persist the correct answer in the JSON payload (storage-only,
            # not rendered by the frontend) so it can be used later for
            # answer-checking, analytics, or export.
            if correct_answer_raw is not None:
                ca = str(correct_answer_raw).strip()
                ca = self._strip_ai_hallucinations(ca)
                ca = self._normalize_math_text(ca)
                if self.mathjax_format == "tags":
                    ca = self._convert_to_mathjax_tags(ca)
                normalized["correct_answer"] = ca
            elif "correct_answer" in data:
                # Already in options-only format but caller included correct_answer key
                ca = str(data["correct_answer"]).strip()
                ca = self._strip_ai_hallucinations(ca)
                ca = self._normalize_math_text(ca)
                if self.mathjax_format == "tags":
                    ca = self._convert_to_mathjax_tags(ca)
                normalized["correct_answer"] = ca

            # Preserve metadata keys (starting with '_')
            for k, v in data.items():
                if k.startswith("_") and k not in normalized:
                    normalized[k] = v

            return normalized
        
        # Handle keyed structure (e.g. c1, c2)
        normalized = {}
        for k, v in data.items():
            if isinstance(v, dict):
                normalized[k] = self.normalize_hint_data(v)
            elif k.startswith("_"):
                normalized[k] = v
            else:
                pass # skip unknown fields
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
        """Extracts front and back content for AI context.
        Uses the first field as Front and all others as Back context."""
        model_name = note.model()["name"]
        fields = list(note.items())
        if not fields:
            return "", ""

        front = fields[0][1]
        back = ""
        
        # If it's a Cloze card, we focus on the specific cloze
        if "cloze" in model_name.lower():
            front, back = self._focus_current_cloze(front, card)
            if not back:
                return "", ""
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

        answers_map = {} # {original_pos: cleaned_ans}

        ACTIVE_MARKER_START = "@@@AI_HINTS_ACTIVE_START@@@"
        ACTIVE_MARKER_END = "@@@AI_HINTS_ACTIVE_END@@@"

        def resolve_cloze_match(match_text: str, start_pos_in_original: int) -> str:
            """Resolves a single {{c1::answer::hint}} block."""
            inner = match_text[2:-2]
            parts = inner.split("::", 1)
            if len(parts) < 2:
                return match_text
            
            tag = parts[0]
            content_with_hint = parts[1]
            
            c_parts = content_with_hint.rsplit("::", 1)
            if len(c_parts) > 1:
                answer = c_parts[0]
                hint = c_parts[1]
            else:
                answer = content_with_hint
                hint = ""
                
            try:
                num_match = re.search(r"\d+", tag)
                number = int(num_match.group()) if num_match else 0
            except (ValueError, AttributeError):
                return match_text

            if number != cloze_number:
                return answer

            # This IS the active cloze.
            cleaned_ans = self._clean_html(answer)
            answers_map[start_pos_in_original] = cleaned_ans
            
            res = f"{ACTIVE_MARKER_START}{answer}"
            if hint:
                res += f" (existing hint: {hint})"
            res += ACTIVE_MARKER_END
            return res

        def process_recursive(content: str) -> str:
            """Iteratively resolves the innermost clozes first."""
            iteration_limit = 50
            while iteration_limit > 0:
                matches = list(re.finditer(r"\{\{c\d+::", content))
                if not matches:
                    break
                
                found_any = False
                for m in reversed(matches):
                    start_pos = m.start()
                    end_pos = content.find("}}", start_pos)
                    if end_pos != -1:
                        cloze_text = content[start_pos:end_pos+2]
                        # We track the original position to keep answers in order
                        # (approximate since content shifts, but relative order holds)
                        resolved = resolve_cloze_match(cloze_text, start_pos)
                        content = content[:start_pos] + resolved + content[end_pos+2:]
                        found_any = True
                        break
                
                if not found_any:
                    break
                iteration_limit -= 1
            
            content = content.replace(ACTIVE_MARKER_START, "Current cloze deletion: ")
            content = content.replace(ACTIVE_MARKER_END, "")
            return content

        focused_text = process_recursive(text)
        # Sort answers by their original discovered position
        sorted_answers = [answers_map[k] for k in sorted(answers_map.keys())]
        return focused_text, ", ".join(sorted_answers)

    def update_note_with_hints(self, note, data: Dict[str, List[str]], toggles: Dict[str, bool] = None, card=None, skip_if_exists: bool = False) -> bool:
        """Appends or replaces the AI hints block in the target field."""
        if not data or (not data.get("hints") and not data.get("options")):
            return False

        # Safety check: Abort if data exists and we were instructed not to overwrite
        if skip_if_exists:
            existing = self.find_hints_block(note, card)
            if existing:
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
        # 1. First, try to find ANY existing block (JSON or HTML) that matches THIS specific card.
        # This is the most surgical update.
        pattern = re.compile(
            rf'<div\b[^>]*class=["\'][^"\']*(?:{self.json_class}|{self.container_class})[^"\']*["\'][^>]*>(.*?)</div>',
            flags=re.DOTALL | re.IGNORECASE,
        )
        matches = list(pattern.finditer(current_val))
        
        # Priority 1: Update block that specifically matches this card
        for match in matches:
            block_html = match.group(0)
            if self._block_matches_card(block_html, card):
                # Found it! Now check if it's JSON or HTML.
                if self.json_class in block_html:
                    try:
                        raw_payload = match.group(1)
                        parsed = self._parse_json_payload(raw_payload)
                        if not isinstance(parsed, dict): parsed = {}
                        
                        # Merge or set data
                        if card_key:
                             # Ensure it is keyed
                             if not self._is_keyed_payload(parsed):
                                  if "hints" in parsed or "options" in parsed:
                                       parsed = {"c1": parsed}
                                  else:
                                       parsed = {}
                             parsed[card_key] = new_data
                        else:
                             parsed.update(new_data)
                             
                        new_payload = html.escape(json.dumps(parsed), quote=False)
                        new_attrs = self._build_attrs(toggles, card if not card_key else None)
                        new_block = f'<div class="{self.json_class}" {new_attrs} style="display:none">{new_payload}</div>'
                        return current_val[:match.start()] + new_block + current_val[match.end():]
                    except:
                        pass
                
                # If it matched card but was HTML-only or failed JSON parse, replace it entirely.
                new_block = self.build_hints_block({card_key: new_data} if card_key else new_data, toggles, card)
                return current_val[:match.start()] + new_block + current_val[match.end():]

        # Priority 2: Update ANY universal keyed block found in the note
        if card_key:
            for match in matches:
                block_html = match.group(0)
                if self.json_class in block_html:
                    try:
                        raw_payload = match.group(1)
                        parsed = self._parse_json_payload(raw_payload)
                        if isinstance(parsed, dict) and self._is_keyed_payload(parsed):
                            # It's a keyed block but didn't match card_id/ord (maybe card was generated without scope)
                            # We update it anyway to keep all hints in one block.
                            parsed[card_key] = new_data
                            new_payload = html.escape(json.dumps(parsed), quote=False)
                            new_attrs = self._build_attrs(toggles, None) # keep universal
                            new_block = f'<div class="{self.json_class}" {new_attrs} style="display:none">{new_payload}</div>'
                            return current_val[:match.start()] + new_block + current_val[match.end():]
                    except:
                        pass

        # 3. No match found: Append new block
        payload = {card_key: new_data} if card_key else new_data
        content_block = self.build_hints_block(payload, toggles, card if not card_key else None)
        if not current_val.strip():
            return content_block
        return current_val.strip() + "\n\n" + content_block

    def build_hints_block(self, data: Dict[str, List[str]], toggles: Dict[str, bool] = None, card=None) -> str:
        """Build the persisted/injected hints block for the configured storage mode."""
        data = self.normalize_hint_data(data)
        attrs = self._build_attrs(toggles, card)
        if self.storage_mode == "json":
            payload = html.escape(json.dumps(data), quote=False)
            return f'<div class="{self.json_class}" {attrs} style="display:none">{payload}</div>'
        return self._build_html_block(data, attrs)

    def _find_target_field(self, note) -> Optional[str]:
        # User requested to ALWAYS save to the first field of all cards
        # because other fields might not render in front of card.
        note_keys = list(note.keys())
        if not note_keys:
            return None
        return note_keys[0]

    def _build_attrs(self, toggles: Dict[str, bool] = None, card=None) -> str:
        attrs = [f'data-ai-hints-addon-id="2119980872"', 'contenteditable="false"']
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
        # More flexible regex for class matching (allows any order of classes)
        pattern = re.compile(
            rf'<div\b[^>]*class=["\'][^"\']*(?:{self.json_class}|{self.container_class})[^"\']*["\'][^>]*>(.*?)</div>',
            flags=re.DOTALL | re.IGNORECASE,
        )
        
        # Anki Note objects have a .fields attribute (list of strings)
        fields = getattr(note, "fields", [])
        if not fields and hasattr(note, "values"):
            try:
                fields = list(note.values())
            except Exception:
                fields = []
        
        for f_val in fields:
            if not isinstance(f_val, str):
                continue
            for match in pattern.finditer(f_val):
                block = match.group(0)
                # Check if this block is scoped to the card
                if self._block_matches_card(block, card):
                    # Check if the block actually HAS data for this specific card
                    if self._json_block_has_data_for_card(block, match.group(1), card):
                        return block
        return None

    def find_all_hints_blocks(self, note) -> List[str]:
        """Extracts all AI hints blocks from all fields of the note."""
        pattern = re.compile(
            rf'<div\b[^>]*class=["\'][^"\']*(?:{self.json_class}|{self.container_class})[^"\']*["\'][^>]*>.*?</div>',
            flags=re.DOTALL | re.IGNORECASE,
        )
        
        blocks = []
        fields = list(note.values()) if hasattr(note, "values") else getattr(note, "fields", [])
        for f_val in fields:
            if not isinstance(f_val, str):
                continue
            for match in pattern.finditer(f_val):
                blocks.append(match.group(0))
        return blocks

    def _extract_all_hints_from_fields(self, note) -> List[Dict[str, Any]]:
        """Scans all fields and returns a list of parsed data objects with metadata."""
        raw_blocks = self.find_all_hints_blocks(note)
        extracted = []
        
        for block in raw_blocks:
            # Extract payload
            match = re.search(r'>(.*?)</div>', block, re.DOTALL)
            if not match:
                continue
            
            raw_payload = match.group(1)
            try:
                parsed = self._parse_json_payload(raw_payload)
            except Exception:
                continue

            # Extract toggles and addon ID
            toggles = {}
            if 'data-ai-show-hints="true"' in block: toggles["hints"] = True
            if 'data-ai-show-options="true"' in block: toggles["options"] = True
            
            if self._is_keyed_payload(parsed):
                for card_key, data in parsed.items():
                    extracted.append({
                        "data": data,
                        "card_key": card_key,
                        "toggles": toggles
                    })
            else:
                # Universal/Legacy block
                extracted.append({
                    "data": parsed,
                    "card_key": None,
                    "toggles": toggles
                })
        return extracted

    def _extract_hints_from_field(self, field_val: str, card_key: Optional[str] = None) -> List[Dict[str, Any]]:
        """Extracts AI data from a single field string."""
        if not isinstance(field_val, str):
            return []
            
        pattern = re.compile(
            rf'<div\b[^>]*class=["\'][^"\']*(?:{self.json_class}|{self.container_class})[^"\']*["\'][^>]*>.*?</div>',
            flags=re.DOTALL | re.IGNORECASE,
        )
        
        extracted = []
        for match in pattern.finditer(field_val):
            block = match.group(0)
            inner_match = re.search(r'>(.*?)</div>', block, re.DOTALL)
            if not inner_match:
                continue
            
            try:
                parsed = self._parse_json_payload(inner_match.group(1))
            except Exception:
                continue
                
            if self._is_keyed_payload(parsed):
                if card_key:
                    if card_key in parsed:
                        extracted.append({"data": parsed[card_key], "card_key": card_key})
                else:
                    for k, v in parsed.items():
                        extracted.append({"data": v, "card_key": k})
            else:
                if not card_key:
                    extracted.append({"data": parsed, "card_key": None})
                    
        return extracted

    def _remove_all_hints_from_fields(self, note) -> bool:
        """Forcefully removes all AI hints blocks from all fields of the note."""
        pattern = re.compile(
            r'(?:[\s\n\r]|<br\s*/?>|&nbsp;|<div>\s*</div>)*<div\b[^>]*class=["\'][^"\']*(?:ai-hints-json|ai-hints-container)[^"\']*["\'][^>]*>.*?</div>(?:[\s\n\r]|<br\s*/?>|&nbsp;|<div>\s*</div>)*',
            flags=re.DOTALL | re.IGNORECASE,
        )
        cleared = False
        for f_name in note.keys():
            val = note[f_name]
            if not isinstance(val, str):
                continue
            new_val = re.sub(pattern, "", val)
            if new_val != val:
                note[f_name] = new_val.strip()
                cleared = True
        return cleared

    def clear_hints_from_note(self, note, card=None) -> bool:
        """Removes AI hints blocks matching the card from all fields, including HTML line breaks."""
        # Regex updated to match leading/trailing whitespace, <br> tags, and &nbsp;
        # We use a greedy match for surrounding whitespace to clean up as much as possible
        ws_pattern = r'(?:[\s\n\r]|<br\s*/?>|&nbsp;|<div>\s*</div>)*'
        pattern = re.compile(
            rf'{ws_pattern}<div\b[^>]*class=["\'][^"\']*(?:{self.json_class}|{self.container_class})[^"\']*["\'][^>]*>(.*?)</div>{ws_pattern}',
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
                                # We only replace the inner payload, keep the outer div
                                inner_match = re.search(r'>(.*?)</div>', block_html, re.DOTALL)
                                if inner_match:
                                    new_block = block_html.replace(inner_match.group(1), new_payload)
                                    new_val = new_val[:match.start()] + new_block + new_val[match.end():]
                                    field_cleared = True
                                    continue
                            # Else if empty, fall through to full removal
                        elif isinstance(parsed, dict) and self._is_keyed_payload(parsed):
                            continue
                    except Exception:
                        pass

                if self._block_matches_card(block_html, card):
                    # Replace the entire matched block (including surrounding <br>/whitespace) with a single newline or nothing
                    new_val = new_val[:match.start()] + new_val[match.end():]
                    field_cleared = True
            
            if field_cleared:
                # Systematic cleanup of multiple <br> tags at the end of the field
                new_val = re.sub(r'(?:<br\s*/?>|\s|&nbsp;)+$', '', new_val, flags=re.IGNORECASE)
                note[f_name] = new_val.strip()
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

        return current_val.strip() + "\n\n" + content_block

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
            # HTML-only blocks always count as having data (we don't know what's in them)
            return True

        card_ord = self._card_ord(card)
        
        try:
            parsed = self._parse_json_payload(raw_payload)
        except Exception:
            # Corrupt JSON: count as NO data so we can replace/append
            return False

        if not isinstance(parsed, dict) or not parsed:
            return False

        if self._is_keyed_payload(parsed):
            if card_ord is None:
                # If no card provided, just check if ANY keys exist
                return bool(parsed)
            return f"c{card_ord + 1}" in parsed
            
        # Legacy/Universal block: check for hints/options
        has_hints = bool(parsed.get("hints")) or bool(parsed.get("options"))
        
        if (
            has_hints
            and not self._block_has_card_scope(block)
            and card_ord is not None
            and card_ord > 0
        ):
            # Legacy blocks only match c1
            return False
            
        return has_hints

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
