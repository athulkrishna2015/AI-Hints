import os
import json
import time
import threading
from typing import List, Dict, Set, Any
from aqt import mw
from aqt.utils import tooltip, info
from aqt.qt import QTimer

from .logger import logger
from .ai_client import AIClient
from .card_parser import CardParser

ADDON_PATH = os.path.dirname(__file__)
STATE_FILE = os.path.join(ADDON_PATH, "batch_state.json")

class BatchManager:
    def __init__(self):
        self.jobs = {} # Format: { job_name: { "created_at": time, "card_ids": [] } }
        self.timer = None
        self._polling_lock = threading.Lock()
        self.load_state()

    def load_state(self):
        if not os.path.exists(STATE_FILE):
            self.jobs = {}
            return
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                self.jobs = json.load(f)
        except Exception as e:
            logger.error(f"AI-Hints BatchManager failed load: {e}")
            self.jobs = {}

    def save_state(self):
        try:
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(self.jobs, f, indent=2)
        except Exception as e:
            logger.error(f"AI-Hints BatchManager failed save: {e}")

    def register_job(self, job_name: str, card_ids: List[int]):
        self.jobs[job_name] = {
            "created_at": int(time.time()),
            "card_ids": [int(cid) for cid in card_ids]
        }
        self.save_state()
        logger.info(f"AI-Hints: Registered batch job {job_name} for {len(card_ids)} cards.")
        self.start_timer_if_needed()

    def start_timer_if_needed(self):
        if not self.jobs:
            return
        if self.timer and self.timer.isActive():
            return
        
        # Start dynamic polling
        self.timer = QTimer(mw)
        self.timer.timeout.connect(self.poll_all_jobs_async)
        # Poll every 10 minutes (Batch is slow, no need to spam)
        self.timer.start(10 * 60 * 1000) 
        logger.info("AI-Hints: Activated Batch Timer.")

    def poll_all_jobs_async(self):
        if not self.jobs:
            if self.timer:
                self.timer.stop()
            return
            
        threading.Thread(target=self._background_poll, daemon=True).start()

    def _background_poll(self):
        if not self._polling_lock.acquire(blocking=False):
            return # Already polling
        
        try:
            config = mw.addonManager.getConfig(os.path.basename(ADDON_PATH)) or {}
            client = AIClient(config)
            
            # Iterate copy of jobs keys to safe deletion
            for job_name in list(self.jobs.keys()):
                try:
                    status = client.get_gemini_batch_status(job_name)
                    state = status.get("state", "UNKNOWN")
                    logger.info(f"AI-Hints Batch {job_name} current state: {state}")
                    
                    if state == "JOB_STATE_SUCCEEDED":
                        logger.info(f"AI-Hints Batch {job_name} has succeeded! Loading data...")
                        self._process_completed_batch(job_name, status)
                    elif state in ("JOB_STATE_FAILED", "JOB_STATE_CANCELLED", "JOB_STATE_EXPIRED"):
                        err = status.get("error", {}).get("message", "Unknown error")
                        logger.error(f"AI-Hints Batch {job_name} ended with failure: {state}. Detail: {err}")
                        mw.taskman.run_on_main(lambda j=job_name, st=state: tooltip(f"AI-Hints Batch Job {j} {st.replace('JOB_STATE_', '')}"))
                        del self.jobs[job_name]
                        mw.taskman.run_on_main(self.save_state)
                except Exception as e:
                    logger.error(f"AI-Hints Error during polling batch {job_name}: {e}")
        finally:
            self._polling_lock.release()

    def _process_completed_batch(self, job_name: str, full_payload: Dict):
        # Dest contains results array
        dest = full_payload.get("dest", {})
        # In REST API, field is inlinedResponses (or nested depending on raw map)
        # The web search confirm it's inlinedResponses. Let's be robust to case
        raw_responses = dest.get("inlinedResponses") or dest.get("inlined_responses", [])
        
        if not raw_responses:
            logger.warning(f"AI-Hints Batch {job_name} had SUCCEEDED state but no inlinedResponses payload found in dest.")
            return
            
        logger.info(f"AI-Hints processing {len(raw_responses)} raw response elements from batch.")
        
        parsed_results = {} # Map str(CardID) -> data_dict
        
        config = mw.addonManager.getConfig(os.path.basename(ADDON_PATH)) or {}
        client = AIClient(config)
        parser = CardParser(
            config.get("target_fields", []),
            config.get("note_type_fields", {}),
            config.get("storage_mode", "json"),
            mathjax_format=config.get("mathjax_format", "delimiters"),
            fix_latex=config.get("fix_latex", False)
        )
        
        for item in raw_responses:
            metadata = item.get("metadata", {})
            key = metadata.get("key")
            if not key:
                continue
            
            resp_body = item.get("response")
            if not resp_body:
                # Failed specific item?
                continue
                
            try:
                content = client._extract_content(resp_body)
                data = client._parse_json_result(content)
                if data.get("hints") or data.get("options") or data.get("distractors"):
                     data = parser.normalize_hint_data(data)
                     from .reviewer_hooks import _ADDON_VERSION # Safe late import
                     if _ADDON_VERSION:
                         data["_version"] = _ADDON_VERSION
                     parsed_results[str(key)] = data
            except Exception as e:
                logger.error(f"AI-Hints: Failed to extract one response item in batch {job_name} (key={key}): {e}")
        
        # Final application to database MUST occur on main loop
        mw.taskman.run_on_main(lambda: self._apply_results_to_db(job_name, parsed_results, config))

    def _apply_results_to_db(self, job_name: str, results: Dict[str, Any], config: Dict):
        try:
            if not results:
                logger.warning(f"AI-Hints Batch {job_name} yielded 0 parseable answers.")
                if job_name in self.jobs:
                    del self.jobs[job_name]
                self.save_state()
                return
                
            logger.info(f"AI-Hints Applying {len(results)} database batch writes.")
            
            parser = CardParser(
                config.get("target_fields", []),
                config.get("note_type_fields", {}),
                config.get("storage_mode", "json"),
                mathjax_format=config.get("mathjax_format", "delimiters"),
                fix_latex=config.get("fix_latex", False)
            )
            
            applied_count = 0
            notes_to_flush = {} # note_id -> note object
            
            toggles = {
                "show_hints_button": config.get("show_hints_button", True),
                "show_options_button": config.get("show_options_button", True)
            }
            
            from .reviewer_hooks import _get_card_from_collection # helper exists there
            
            for card_id_str, data in results.items():
                try:
                    cid = int(card_id_str)
                    card = _get_card_from_collection(cid)
                    if not card:
                        continue
                    
                    note = card.note()
                    if parser.update_note_with_hints(note, data, toggles, card):
                        notes_to_flush[note.id] = note
                        applied_count += 1
                except Exception as e:
                     logger.error(f"Error loading card {card_id_str} during batch apply: {e}")

            # Bulk flush
            for note in notes_to_flush.values():
                 mw.col.update_note(note)
            
            if applied_count > 0:
                try:
                    mw.col.autosave()
                except: pass
                
            # Success cleanup!
            if job_name in self.jobs:
                del self.jobs[job_name]
            self.save_state()
            
            info(f"✨ AI-Hints: Batch job completed! Successfully updated {applied_count} cards across {len(notes_to_flush)} notes.")
            logger.info(f"AI-Hints: Final cleanup of Batch {job_name} complete.")
            
            # Stop timer if empty
            if not self.jobs and self.timer:
                self.timer.stop()
                
            # Force UI sync
            if mw.reviewer and mw.reviewer.card:
                # Slight chance current card was in the batch update
                from .reviewer_hooks import refresh_current_card
                refresh_current_card()

        except Exception as e:
            logger.error(f"AI-Hints Critical error finalizing batch {job_name} write to DB: {e}")

# Global instance singleton
batch_manager = BatchManager()

def initialize_batch_manager():
    """Call on addon setup to resume outstanding polling if needed."""
    batch_manager.start_timer_if_needed()
