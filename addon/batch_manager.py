import os
import json
import time
import threading
from typing import List, Dict, Set, Any
from aqt import mw
from aqt.qt import QTimer
from .logger import logger, info, tooltip
from .ai_client import AIClient
from .card_parser import CardParser

ADDON_PATH = os.path.dirname(__file__)
STATE_FILE = os.path.join(ADDON_PATH, "batch_state.json")

class BatchManager:
    def __init__(self):
        self.jobs = {} # Format: { job_name: { "created_at": time, "card_ids": [] } }
        self.timer = None
        self._polling_lock = threading.Lock()
        
        # Sequential Queue Runtime State
        self.local_queue = []
        self.local_queue_total = 0
        self.local_queue_active = False
        self.local_queue_paused = False
        self.local_queue_errors = 0
        self.saved_config = {}
        self.saved_provider = None
        
        # Live Runtime Diagnostic Hooks
        self.current_local_cid = None
        self.current_local_model = ""
        
        self.load_state()

    def load_state(self):
        if not os.path.exists(STATE_FILE):
            self.jobs = {}
            return
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Detect new nested structure vs legacy plain jobs dict
            if isinstance(data, dict) and ("native_jobs" in data or "local_cache" in data):
                self.jobs = data.get("native_jobs", {})
                
                # Restore Local Sequential Cache state
                cache = data.get("local_cache", {})
                if cache and isinstance(cache, dict):
                     self.local_queue = cache.get("queue", [])
                     self.local_queue_total = cache.get("total", len(self.local_queue))
                     self.local_queue_errors = cache.get("errors", 0)
                     self.saved_config = cache.get("config", {})
                     self.saved_provider = cache.get("provider", None)
                     logger.info(f"BatchManager restored paused local queue: {len(self.local_queue)} items remaining.")
            else:
                # Legacy format
                self.jobs = data if isinstance(data, dict) else {}
                
        except Exception as e:
            logger.error(f"AI-Hints BatchManager failed load: {e}")
            self.jobs = {}

    def save_state(self):
        try:
            # Package combined persisted bundle
            payload = {
                "native_jobs": self.jobs,
                "local_cache": {
                    "queue": self.local_queue,
                    "total": self.local_queue_total,
                    "errors": self.local_queue_errors,
                    "config": getattr(self, "saved_config", {}),
                    "provider": getattr(self, "saved_provider", None)
                }
            }
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
        except Exception as e:
            logger.error(f"AI-Hints BatchManager failed save: {e}")

    def get_status_summary(self) -> str:
        """Builds rich contextual HTML summary of queue activity."""
        html_parts = []
        
        if self.local_queue_active:
            remaining = len(self.local_queue)
            done = self.local_queue_total - remaining
            status_txt = "<span style='color:#ffc107;'><b>⏸️ PAUSED</b></span>" if self.local_queue_paused else "<span style='color:#28a745;'><b>🔥 ACTIVE</b></span>"
            
            html_parts.append(f"<div style='font-size:12px; padding-bottom:4px;'>{status_txt} <b>Local Sequential Queue</b></div>")
            html_parts.append(f"📊 Progress: <b>{done}</b> / {self.local_queue_total} cards generated. ({remaining} left)<br/>")
            
            if self.current_local_model:
                 html_parts.append(f"🤖 Model: <code>{self.current_local_model}</code><br/>")
                 
            if self.current_local_cid:
                 # Explicitly provide HTML clickable navigation link
                 html_parts.append(f"🔎 Currently Processing: <a href='browse:cid:{self.current_local_cid}' style='color: #007bff;'>[View Card {self.current_local_cid}]</a><br/>")
            
            html_parts.append("<hr style='border:0; border-top:1px solid #ccc; margin:8px 0;'/>")

        elif self.local_queue:
            # Persisted but inactive
            remaining = len(self.local_queue)
            done = self.local_queue_total - remaining
            html_parts.append(f"💾 <b style='color:#fd7e14;'>Saved Dormant Queue</b> ({remaining} cards pending)<br/>")
            html_parts.append(f"Completed so far: {done} / {self.local_queue_total} total.<br/>")
            html_parts.append("<i>Click 'Resume Saved Queue' below to restart.</i><br/><br/>")

        if not self.jobs:
            if not html_parts:
                return "<div style='color:#6c757d; font-style:italic;'>No active batch jobs are currently running or pending.</div>"
        else:
            html_parts.append("<b>### Ongoing Cloud Batches:</b><br/>")
            now = time.time()
            for name, details in self.jobs.items():
                elapsed = int(now - details.get("created_at", now))
                minutes = elapsed // 60
                cards = len(details.get("card_ids", []))
                html_parts.append(f"🔹 <b>{name}</b>: {cards} cards queued ({minutes} mins ago)<br/>")
        
        return "\n".join(html_parts)

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
                    # Safety gate: If user generated data while batch was running, DO NOT OVERWRITE.
                    if parser.update_note_with_hints(note, data, toggles, card, skip_if_exists=True):
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

    def start_local_sequential_queue(self, card_ids: List[int] = None, config: Dict[str, Any] = None, provider_override: str = None):
        """Launches/Resumes a background thread loop to run sequential generation."""
        if self.local_queue_active:
             info("⚠️ Another Local Queue is already active! Wait for it to finish.")
             return False
        
        # 🚀 RESUME Logic
        if card_ids is None:
             if not self.local_queue:
                  logger.warning("Requested local queue resume but queue was empty.")
                  return False
             logger.info(f"Resuming local queue with {len(self.local_queue)} items.")
             # Use previously persisted config/provider
             config = self.saved_config or config
             provider_override = self.saved_provider
        else:
             # 🆕 START FRESH Logic
             self.local_queue = list(card_ids)
             self.local_queue_total = len(card_ids)
             self.local_queue_errors = 0
             self.saved_config = config or {}
             self.saved_provider = provider_override
        
        if not config:
             logger.error("Cannot start background queue without valid config map.")
             return False

        self.local_queue_active = True
        self.local_queue_paused = False # Explicitly ensure unpaused on resume
        
        # Immediately persist setup state to disk in case of crash 1ms later
        self.save_state()
        
        # Fire and forget daemon
        t = threading.Thread(
            target=self._run_local_queue,
            args=(config, provider_override),
            daemon=True
        )
        t.start()
        return True

    def stop_local_queue(self):
        """Requests the background worker to halt immediate next-loop."""
        if not self.local_queue_active:
             # Wipe persistent cache even if thread isn't running (force clear saved state)
             self.local_queue = []
             self.save_state()
             return True
             
        self.local_queue_active = False
        self.local_queue_paused = False
        self.local_queue = [] # Clear remaining list
        self.save_state() # Persist full stop clearing cache
        logger.info("Local Sequential Queue ABORT manually triggered by user.")
        return True

    def set_pause_local_queue(self, pause_state: bool):
        """Sets global loop gate status."""
        self.local_queue_paused = pause_state
        logger.info(f"Local Queue Pause set to: {pause_state}")

    def _run_local_queue(self, config: Dict, provider_override: str):
        """Core iterative engine thread that drives the sequential queue."""
        logger.info(f"STARTING local sequential queue for {self.local_queue_total} cards.")
        
        # Instantiate client and parser fresh in this thread environment
        client = AIClient(config)
        parser = CardParser(
            config.get("target_fields", []),
            config.get("note_type_fields", {}),
            config.get("storage_mode", "json")
        )
        
        # 🔍 Snapshot runtime model diagnostics for display
        target_prov = provider_override or config.get("ai_provider", "openai")
        try:
             models = client._models_for_provider(target_prov)
             self.current_local_model = models[0] if models else "Unknown"
        except: self.current_local_model = "Unknown"
        
        from .reviewer_hooks import _get_card_from_collection
        
        # Loop until empty or deactivated
        while self.local_queue and self.local_queue_active:
            # 🚦 GATE CHECK: If user paused, idle wait without consuming
            if self.local_queue_paused:
                 time.sleep(1)
                 continue
                 
            if not self.local_queue:
                 continue

            cid = self.local_queue[0] # Peek first
            self.current_local_cid = cid # Post to diagnostic hook
            
            try:
                card = _get_card_from_collection(cid)
                if not card:
                    if self.local_queue:
                        self.local_queue.pop(0)
                        self.save_state() # Persist skip
                    continue
                
                # 1. Prep input
                front_txt, back_txt = parser.get_note_content(card.note(), card)
                final_sys = config.get("system_prompt", "")
                final_usr = f"FRONT:\n{front_txt}\n\nBACK:\n{back_txt}"
                
                # 2. Execute standard generation path (respects fallbacks automatically)
                # We enforce provider override if explicitly requested
                if provider_override and provider_override != "Standard Config (Follows Fallback Matrix)":
                    resp_data = client.generate_options(front_txt, back_txt, override_provider=provider_override)
                else:
                    resp_data = client.generate_options(front_txt, back_txt)
                
                if resp_data and (resp_data.get("hints") or resp_data.get("options")):
                    # 3. Apply directly to db using our concurrent-safe update method!
                    def _apply_on_main(note, d):
                        # Apply directly inside main thread loop to avoid col collisions
                        if parser.update_note_with_hints(note, d, skip_if_exists=True):
                            mw.col.update_note(note)
                            return True
                        return False

                    # We need to execute write inside the main UI loop for Anki safety
                    note = card.note()
                    mw.taskman.run_on_main(lambda n=note, d=resp_data: _apply_on_main(n, d))
                    
                else:
                    self.local_queue_errors += 1
                    
            except Exception as e:
                logger.error(f"Local Queue Card Error {cid}: {e}")
                self.local_queue_errors += 1
            
            # Pop and cycle
            if self.local_queue:
                self.local_queue.pop(0)
                self.save_state() # Continuous checkpointing!
            
            # Dynamic pacing to respect generic rate limits (e.g. 1.5s per generation)
            time.sleep(1.5)

        # Completion Cleanup
        self.local_queue_active = False
        self.current_local_cid = None
        self.current_local_model = ""
        self.save_state() # Confirm final wipe of local cache from disk
        logger.info(f"FINISHED local sequential queue. Total={self.local_queue_total}, Errors={self.local_queue_errors}")
        
        def _finished_notify():
             info(f"✅ Sequential Background Generation Complete!\nTotal: {self.local_queue_total}\nFailed/Skipped: {self.local_queue_errors}")
             # Auto-save deck
             try: mw.col.autosave()
             except: pass

        mw.taskman.run_on_main(_finished_notify)

# Global instance singleton
batch_manager = BatchManager()

def initialize_batch_manager():
    """Call on addon setup to resume outstanding polling if needed."""
    batch_manager.start_timer_if_needed()
