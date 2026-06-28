import os
import json
import time
import threading
from typing import List, Dict, Set, Any
from aqt import mw
from aqt.qt import QTimer
from .logger import logger, info, tooltip, state
from .ai_client import AIClient
from .card_parser import CardParser

ADDON_PATH = os.path.dirname(__file__)

class BatchManager:
    def __init__(self):
        self.jobs = {} # Format: { job_name: { "created_at": time, "card_ids": [] } }
        self.timer = None
        self.card_attempts = {}
        self.active_providers = []
        self._polling_lock = threading.Lock()
        
        # Sequential Queue Runtime State
        self.local_queue = []
        self.local_queue_total = 0
        self.local_queue_active = False
        self.local_queue_paused = False
        self.local_queue_errors = 0
        self.local_queue_pass = 1
        self.local_queue_failed_cards = []
        self.saved_config = {}
        self.saved_provider = None
        
        # Live Runtime Diagnostic Hooks
        self.current_local_cid = None
        self.current_local_model = ""
        self.current_local_provider = ""
        self.last_run_stats = None
        
        self.active_threads_status = {}
        self._db_lock = threading.RLock()
        
        self.load_state()

    def _state_file_path(self) -> str:
        """Returns the path to the batch state file, storing it in the active profile directory if available."""
        try:
            from aqt import mw
            if mw is not None and "Mock" not in type(mw).__name__ and getattr(mw, "pm", None) is not None:
                profile_dir = mw.pm.profileFolder()
                if profile_dir:
                    return os.path.join(profile_dir, "ai_hints_batch_state.json")
        except Exception:
            pass
        return os.path.join(ADDON_PATH, "batch_state.json")

    def load_state(self):
        state_file = self._state_file_path()
        if not os.path.exists(state_file):
            self.jobs = {}
            return
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Detect new nested structure vs legacy plain jobs dict
            if isinstance(data, dict) and ("native_jobs" in data or "local_cache" in data):
                self.jobs = data.get("native_jobs", {})
                
                # Restore Local Sequential Cache state
                cache = data.get("local_cache", {})
                if cache and isinstance(cache, dict):
                     self.local_queue = cache.get("queue", [])
                     self.local_queue_total = cache.get("total", len(self.local_queue))
                     self.local_queue_active = cache.get("active", False)
                     self.local_queue_paused = cache.get("paused", False)
                     self.local_queue_errors = cache.get("errors", 0)
                     self.local_queue_pass = cache.get("pass", 1)
                     self.local_queue_failed_cards = cache.get("failed_cards", [])
                     self.saved_config = cache.get("config", {})
                     self.saved_provider = cache.get("provider", None)
                     self.last_run_stats = cache.get("last_run_stats", None)
                     logger.info(f"BatchManager restored state. Queue: {len(self.local_queue)} items (Active: {self.local_queue_active}, Paused: {self.local_queue_paused}).")
            else:
                # Legacy format
                self.jobs = data if isinstance(data, dict) else {}
                
        except Exception as e:
            logger.error(f"AI-Hints BatchManager failed load: {e}")
            self.jobs = {}

    def save_state(self):
        if not hasattr(self, "_db_lock"):
            self._db_lock = threading.RLock()
        with self._db_lock:
            try:
                # Package combined persisted bundle
                # Strip sensitive API keys from the saved config to prevent redundancy and data exposure.
                # The keys will be re-merged from the main addon config during resume.
                stripped_config = dict(getattr(self, "saved_config", {}))
                if "api_keys" in stripped_config:
                    stripped_config.pop("api_keys")

                payload = {
                    "native_jobs": self.jobs,
                    "local_cache": {
                        "queue": self.local_queue,
                        "total": self.local_queue_total,
                        "errors": self.local_queue_errors,
                        "pass": self.local_queue_pass,
                        "active": self.local_queue_active,
                        "paused": self.local_queue_paused,
                        "failed_cards": getattr(self, "local_queue_failed_cards", []),
                        "config": stripped_config,
                        "provider": getattr(self, "saved_provider", None),
                        "last_run_stats": self.last_run_stats
                    }
                }
                state_file = self._state_file_path()
                with open(state_file, "w", encoding="utf-8") as f:
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
            
            pass_str = f" (Pass #{self.local_queue_pass})" if self.local_queue_pass > 1 else ""
            html_parts.append(f"<div style='font-size:12px; padding-bottom:4px;'>{status_txt} <b>Local Sequential Queue{pass_str}</b></div>")
            html_parts.append(f"📊 Progress: <b>{done}</b> / {self.local_queue_total} cards generated. ({remaining} left)<br/>")
            failed_cards = getattr(self, "local_queue_failed_cards", [])
            if failed_cards:
                 html_parts.append("<div style='margin-top:4px;'>")
                 html_parts.append(f"⚠️ <b>Failed Cards ({len(failed_cards)}):</b> ")
                 links = []
                 for fcid in failed_cards[:15]:
                      links.append(f"<a href='browse:cid:{fcid}' style='color: #dc3545;'>[Card {fcid}]</a>")
                 html_parts.append(", ".join(links))
                 if len(failed_cards) > 15:
                      html_parts.append(f" <i>and {len(failed_cards) - 15} more</i>")
                 html_parts.append("</div>")
            
            active_threads = {}
            if getattr(self, "active_threads_status", None):
                try:
                    active_threads = dict(self.active_threads_status)
                except Exception:
                    pass

            if active_threads:
                 html_parts.append("<div style='margin-top:6px; font-size:11px;'>")
                 html_parts.append("<b>Active Concurrent Threads:</b><br/>")
                 for prov, info in active_threads.items():
                      cid_link = f"<a href='browse:cid:{info['cid']}' style='color: #007bff;'>[Card {info['cid']}]</a>" if info['cid'] else "None"
                      html_parts.append(f"• 🔌 <b>{prov.capitalize()}</b> ({info['model']}): Processing {cid_link}<br/>")
                 html_parts.append("</div>")
            else:
                 if getattr(self, "current_local_provider", None):
                      html_parts.append(f"🔌 Provider: <b>{self.current_local_provider}</b><br/>")

                 if self.current_local_model:
                      html_parts.append(f"🤖 Model: <code>{self.current_local_model}</code><br/>")
                      
                 if self.current_local_cid:
                      # Explicitly provide HTML clickable navigation link
                      html_parts.append(f"🔎 Currently Processing: <a href='browse:cid:{self.current_local_cid}' style='color: #007bff;'>[View Card {self.current_local_cid}]</a><br/>")
            
            if self.local_queue:
                 html_parts.append("<div style='margin-top:6px; font-size:11px;'>")
                 html_parts.append("<b>Pending in Queue (Next 5):</b><br/>")
                 # Use a copy to avoid thread safety issues while iterating
                 with self._db_lock:
                     queue_snapshot = list(self.local_queue[:5])
                     total_remaining = len(self.local_queue)
                 
                 for cid in queue_snapshot:
                      html_parts.append(f"• <a href='browse:cid:{cid}' style='color: #007bff;'>[Card {cid}]</a>")
                      html_parts.append(f" <a href='discard:cid:{cid}' style='color: #dc3545; text-decoration: none;'>[✖ Discard]</a><br/>")
                 
                 if total_remaining > 5:
                      html_parts.append(f"<i>... and {total_remaining - 5} more.</i>")
                 html_parts.append("</div>")

            html_parts.append("<hr style='border:0; border-top:1px solid #ccc; margin:8px 0;'/>")

        elif self.local_queue:
            # Persisted but inactive
            remaining = len(self.local_queue)
            done = self.local_queue_total - remaining
            html_parts.append(f"💾 <b style='color:#fd7e14;'>Saved Dormant Queue</b> ({remaining} cards pending)<br/>")
            html_parts.append(f"Completed so far: {done} / {self.local_queue_total} total.<br/>")
            failed_cards = getattr(self, "local_queue_failed_cards", [])
            if failed_cards:
                 html_parts.append("<div style='margin-top:4px;'>")
                 html_parts.append(f"⚠️ <b>Failed Cards ({len(failed_cards)}):</b> ")
                 links = []
                 for fcid in failed_cards[:15]:
                      links.append(f"<a href='browse:cid:{fcid}' style='color: #dc3545;'>[Card {fcid}]</a>")
                 html_parts.append(", ".join(links))
                 if len(failed_cards) > 15:
                      html_parts.append(f" <i>and {len(failed_cards) - 15} more</i>")
                 html_parts.append("</div>")
            
            if self.local_queue:
                 html_parts.append("<div style='margin-top:6px; font-size:11px;'>")
                 html_parts.append("<b>Pending in Queue (Next 5):</b><br/>")
                 with self._db_lock:
                     queue_snapshot = list(self.local_queue[:5])
                 
                 for cid in queue_snapshot:
                      html_parts.append(f"• <a href='browse:cid:{cid}' style='color: #007bff;'>[Card {cid}]</a>")
                      html_parts.append(f" <a href='discard:cid:{cid}' style='color: #dc3545; text-decoration: none;'>[✖ Discard]</a><br/>")
                 
                 if remaining > 5:
                      html_parts.append(f"<i>... and {remaining - 5} more.</i>")
                 html_parts.append("</div>")

            html_parts.append("<i>Click 'Resume Saved Queue' below to restart.</i><br/><br/>")
            
        elif self.last_run_stats:
            stats = self.last_run_stats
            success = stats['total'] - stats['errors']
            html_parts.append(f"<div style='font-size:12px; padding-bottom:4px;'><span style='color:#28a745;'><b>✅ COMPLETED</b></span> <b>Last Local Queue</b></div>")
            html_parts.append(f"✨ Success: <b>{success}</b> / {stats['total']} cards.<br/>")
            if stats['errors'] > 0:
                html_parts.append(f"⚠️ Errors: <span style='color:#dc3545;'>{stats['errors']}</span><br/>")
                failed_cards = stats.get("failed_cards", [])
                if failed_cards:
                     html_parts.append("<div style='margin-top:4px;'>")
                     html_parts.append("<b>Failed Card IDs:</b> ")
                     links = []
                     for fcid in failed_cards[:15]:
                          links.append(f"<a href='browse:cid:{fcid}' style='color: #dc3545;'>[Card {fcid}]</a>")
                     html_parts.append(", ".join(links))
                     if len(failed_cards) > 15:
                          html_parts.append(f" <i>and {len(failed_cards) - 15} more</i>")
                     html_parts.append("</div>")
            
            finished_at = time.strftime('%H:%M:%S', time.localtime(stats.get('time', 0)))
            html_parts.append(f"🕒 Finished at: {finished_at}<br/>")
            html_parts.append("<hr style='border:0; border-top:1px solid #ccc; margin:8px 0;'/>")

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
                    logger.debug(f"AI-Hints Batch {job_name} current state: {state}")

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
        
        from .config_ui import ADDON_PACKAGE
        config = mw.addonManager.getConfig(ADDON_PACKAGE) or {}
        client = AIClient(config)
        parser = CardParser(
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
                    data["_provider"] = "gemini"
                    gemini_models = client._models_for_provider("gemini")
                    data["_model"] = gemini_models[0] if gemini_models else "gemini-2.5-flash-lite"
                    data["_generated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
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
        state.GLOBAL_STOP = False
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

             # Re-inject fresh API keys from global config if missing in the resumed state.
             # This prevents batch_state.json from needing to store sensitive keys.
             if config and not config.get("api_keys"):
                  try:
                       from aqt import mw
                       # Get addon package name (e.g. 'ai_hints_dev' or 'AI-Hints')
                       pkg = __name__.split(".")[0]
                       global_config = mw.addonManager.getConfig(pkg) or {}
                       config["api_keys"] = global_config.get("api_keys", {})
                  except Exception as e:
                       logger.error(f"Failed to re-inject API keys during batch resume: {e}")
        else:
             # 🆕 START FRESH Logic
             self.local_queue = list(card_ids)
             self.local_queue_total = len(card_ids)
             self.local_queue_errors = 0
             self.local_queue_pass = 1
             self.local_queue_failed_cards = []
             self.saved_config = config or {}
             self.saved_provider = provider_override
             self.last_run_stats = None 
        
        if not config:
             logger.error("Cannot start background queue without valid config map.")
             return False

        self.local_queue_active = True
        if card_ids is not None:
             self.local_queue_paused = False
        
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
             self.last_run_stats = None
             self.save_state()
             return True
             
        self.local_queue_active = False
        self.local_queue_paused = False
        self.local_queue = [] # Clear remaining list
        self.last_run_stats = None
        self.save_state() # Persist full stop clearing cache
        logger.debug("Local Sequential Queue ABORT manually triggered by user.")
        return True

    def stop_all(self):
        """Emergency stop for ALL activity (Local Queue + Cloud Batches)."""
        state.GLOBAL_STOP = True
        logger.info("🚨 EMERGENCY STOP: Aborting all active generations.")
        self.stop_local_queue()
        
        # Clear cloud batches from tracking
        if self.jobs:
            count = len(self.jobs)
            self.jobs = {}
            if self.timer:
                self.timer.stop()
            logger.info(f"Cleared {count} cloud batch jobs from tracking.")
            
        self.save_state()
        tooltip("🛑 All generations stopped.")
        return True

    def set_pause_local_queue(self, pause_state: bool):
        """Sets global loop gate status."""
        self.local_queue_paused = pause_state
        self.save_state()
        logger.info(f"Local Queue Pause set to: {pause_state}")

    def discard_from_queue(self, cid: int):
        """Removes a specific card ID from the queue."""
        with self._db_lock:
            if cid in self.local_queue:
                self.local_queue.remove(cid)
                if hasattr(self, "local_queue_failed_cards") and cid in self.local_queue_failed_cards:
                    try:
                        self.local_queue_failed_cards.remove(cid)
                    except ValueError:
                        pass
                self.save_state()
                return True
        return False

    def _run_local_queue(self, config: Dict, provider_override: str):
        """Core iterative engine thread that drives the sequential queue."""
        logger.info(f"STARTING local sequential queue for {self.local_queue_total} cards.")
        
        self.card_attempts = {}
        self.active_threads_status = {}
        if not hasattr(self, "_db_lock"):
             self._db_lock = threading.RLock()
             
        client = AIClient(config)
        parser = CardParser()
        
        # Keep track of the full set of cards we intend to process
        # This is used for the verification passes.
        original_request = list(self.local_queue)
        from .reviewer_hooks import card_has_hints, _get_card_from_collection

        while self.local_queue_active:
            use_multithread = config.get("multithread_providers", False)
            
            if use_multithread and (not provider_override or provider_override == "Standard Config (Follows Fallback Matrix)"):
                 primary = config.get("ai_provider", "openai")
                 providers = client._candidate_providers(primary)
                 if not providers:
                      logger.error("No configured providers are ready for multithreading.")
                      self.local_queue_active = False
                      self.save_state()
                      return
            else:
                 target_prov = provider_override or config.get("ai_provider", "openai")
                 providers = [target_prov]
                 
            self.active_providers = providers
            logger.info(f"Local Queue Pass #{self.local_queue_pass}: Running with {len(self.local_queue)} cards using providers: {providers}")
            
            threads = []
            for prov in providers:
                 t = threading.Thread(
                      target=self._run_local_queue_thread,
                      args=(prov, client, parser, config),
                      daemon=True
                 )
                 threads.append(t)
                 t.start()
                 
            for t in threads:
                 t.join()
            
            # --- Verification Pass Logic ---
            if not self.local_queue_active:
                break

            # Check if any cards from the original request are still missing hints
            missing_cids = []
            for cid in original_request:
                # We fetch card from collection because its hints might have been updated by other threads/passes
                card = _get_card_from_collection(cid)
                if card and not card_has_hints(card):
                    missing_cids.append(cid)
            
            if not missing_cids:
                # 🏁 All done!
                logger.info(f"Verification Pass: All {len(original_request)} cards successfully have hints now.")
                break
            
            # If we reached here, some cards are still missing. 
            # Re-queue them and start another pass.
            with self._db_lock:
                self.local_queue = list(missing_cids)
                self.local_queue_pass += 1
                self.card_attempts = {} # Reset attempts for new pass
                self.save_state()
            
            logger.info(f"Verification Pass: {len(missing_cids)} cards still missing hints. Starting Pass #{self.local_queue_pass} in 3 seconds...")
            time.sleep(3) # Small cooldown between passes
            
            if self.local_queue_pass > 10:
                logger.warning(f"Batch Sequential Queue reached maximum pass limit (10). Stopping with {len(missing_cids)} cards unfinished.")
                break
             
        self.local_queue_active = False
        self.active_threads_status = {}
        
        # Calculate final error count for stats
        final_missing = []
        for cid in original_request:
            card = _get_card_from_collection(cid)
            if card and not card_has_hints(card):
                final_missing.append(cid)
        
        self.last_run_stats = {
            "total": self.local_queue_total,
            "errors": len(final_missing),
            "failed_cards": list(final_missing),
            "time": time.time()
        }
            
        self.save_state()
        if len(final_missing) == 0:
            logger.info(f"FINISHED local sequential queue. Successfully processed all {self.local_queue_total} cards.")
            mw.taskman.run_on_main(lambda: tooltip("✨ Batch Sequential Queue Finished! All cards processed."))
        else:
            logger.info(f"FINISHED local sequential queue. Processed {self.local_queue_total - len(final_missing)} cards. {len(final_missing)} cards failed after {self.local_queue_pass} passes.")
            mw.taskman.run_on_main(lambda m=len(final_missing): tooltip(f"✨ Batch Finished. {m} cards failed all retry attempts."))

    def _handle_card_failure(self, cid: int, provider: str):
        failed_provs = self.card_attempts.setdefault(cid, [])
        if provider not in failed_provs:
            failed_provs.append(provider)
            
        all_failed = all(p in failed_provs for p in self.active_providers)
        with self._db_lock:
            if all_failed:
                logger.warning(f"Card {cid} failed on all active providers {self.active_providers}. Counting as error.")
                self.local_queue_errors += 1
                if not hasattr(self, "local_queue_failed_cards"):
                    self.local_queue_failed_cards = []
                if cid not in self.local_queue_failed_cards:
                    self.local_queue_failed_cards.append(cid)
                self.save_state()
            else:
                logger.info(f"Card {cid} failed on {provider}. Requeuing for other providers to try.")
                self.local_queue.insert(0, cid)
                self.save_state()

    def _run_local_queue_thread(self, provider: str, client: AIClient, parser: CardParser, config: Dict):
        from .reviewer_hooks import _get_card_from_collection
        
        try:
             models = client._models_for_provider(provider)
             current_model = models[0] if models else "Unknown"
        except:
             current_model = "Unknown"

        logger.info(f"AI-Hints Thread for {provider} started.")
        self.active_threads_status[provider] = {
            "model": current_model,
            "cid": None,
            "status": "Starting"
        }

        while self.local_queue_active:
            if self.local_queue_paused:
                 self.active_threads_status[provider] = {
                     "model": current_model,
                     "cid": None,
                     "status": "⏸️ Paused"
                 }
                 time.sleep(1)
                 continue

            # Check if this provider has any available models (not blacklisted)
            try:
                available_models = client._models_for_provider(provider)
            except Exception:
                available_models = []
            
            if not available_models:
                 with self._db_lock:
                     if not self.local_queue:
                         break
                 self.active_threads_status[provider] = {
                     "model": current_model,
                     "cid": None,
                     "status": "⏳ Rate Limited / Cooldown"
                 }
                 # Sleep and check again later, do not pop a card!
                 time.sleep(2)
                 continue

            cid = None
            should_break = False
            should_sleep = False
            with self._db_lock:
                if not self.local_queue:
                    any_processing = False
                    for prov, status_info in self.active_threads_status.items():
                        if prov != provider and status_info.get("cid") is not None:
                            any_processing = True
                            break
                    if not any_processing:
                        should_break = True
                    else:
                        should_sleep = True
                else:
                    # Find first card that this provider hasn't failed yet
                    found_idx = -1
                    for idx, candidate_cid in enumerate(self.local_queue):
                        failed_provs = self.card_attempts.get(candidate_cid, [])
                        if provider not in failed_provs:
                            found_idx = idx
                            break
                    
                    if found_idx != -1:
                        cid = self.local_queue.pop(found_idx)
                        self.save_state()
                    else:
                        # All remaining cards in the queue have been tried and failed by this provider.
                        # Sleep and try again later
                        should_sleep = True

            if should_break:
                break

            if should_sleep:
                self.active_threads_status[provider] = {
                    "model": current_model,
                    "cid": None,
                    "status": "⏳ Waiting for peers"
                }
                time.sleep(2)
                continue

            if not cid:
                break

            self.active_threads_status[provider] = {
                "model": current_model,
                "cid": cid,
                "status": "Processing"
            }

            try:
                # Retrieve the card payload strictly on Anki's main thread to prevent thread-safety/segfault issues
                payload = {"front": None, "back": None, "exists": False, "error": None}
                evt = threading.Event()

                def _fetch():
                    try:
                        card = _get_card_from_collection(cid)
                        if card:
                            note = card.note()
                            front, back = parser.get_note_content(note, card)
                            payload["front"] = front
                            payload["back"] = back
                            payload["exists"] = True
                        else:
                            payload["exists"] = False
                    except Exception as e:
                        payload["error"] = str(e)
                    finally:
                        evt.set()

                mw.taskman.run_on_main(_fetch)
                evt.wait()

                if payload["error"]:
                    logger.error(f"Error fetching card {cid} content: {payload['error']}")
                    with self._db_lock:
                        self.local_queue_errors += 1
                        if not hasattr(self, "local_queue_failed_cards"):
                            self.local_queue_failed_cards = []
                        if cid not in self.local_queue_failed_cards:
                            self.local_queue_failed_cards.append(cid)
                    continue

                if not payload["exists"]:
                    continue

                if not payload["front"] and not payload["back"]:
                    logger.info(f"AI-Hints: Card {cid} has empty content (e.g. empty fields or missing Cloze deletion). Skipping card and marking as skipped in DB.")
                    resp_data = {"hints": [], "options": [], "_skipped": True}
                    def _apply_skipped_on_main(cid_val, data_dict):
                        try:
                            card = _get_card_from_collection(cid_val)
                            if not card:
                                return
                            note = card.note()
                            config_current = mw.addonManager.getConfig(os.path.basename(ADDON_PATH)) or {}
                            toggles = {
                                "show_hints_button": config_current.get("show_hints_button", True),
                                "show_options_button": config_current.get("show_options_button", True)
                            }
                            if parser.update_note_with_hints(note, data_dict, toggles, card, skip_if_exists=True):
                                mw.col.update_note(note)
                        except Exception as ex:
                            logger.error(f"Error applying skipped results for card {cid_val} on main: {ex}")

                    mw.taskman.run_on_main(lambda c=cid, d=resp_data: _apply_skipped_on_main(c, d))
                    time.sleep(1.5)
                    continue


                front_txt = payload["front"]
                back_txt = payload["back"]

                resp_data = client.generate_options(
                    front_txt, 
                    back_txt, 
                    override_provider=provider, 
                    only_this_provider=True
                )

                if resp_data and (resp_data.get("hints") or resp_data.get("options")):
                    actual_model = resp_data.get("_model")
                    if actual_model:
                        self.active_threads_status[provider]["model"] = actual_model
                    
                    def _apply_on_main(cid_val, data_dict):
                        try:
                            card = _get_card_from_collection(cid_val)
                            if not card:
                                return
                            note = card.note()
                            # Fetch current toggles from active config
                            config_current = mw.addonManager.getConfig(os.path.basename(ADDON_PATH)) or {}
                            toggles = {
                                "show_hints_button": config_current.get("show_hints_button", True),
                                "show_options_button": config_current.get("show_options_button", True)
                            }
                            if parser.update_note_with_hints(note, data_dict, toggles, card, skip_if_exists=True):
                                mw.col.update_note(note)
                                if mw.reviewer and mw.reviewer.card and mw.reviewer.card.id == cid_val:
                                    from .reviewer_hooks import refresh_current_card
                                    refresh_current_card()
                        except Exception as ex:
                            logger.error(f"Error applying results for card {cid_val} on main: {ex}")

                    mw.taskman.run_on_main(lambda c=cid, d=resp_data: _apply_on_main(c, d))
                else:
                    self._handle_card_failure(cid, provider)
            except Exception as e:
                logger.error(f"Local Queue thread ({provider}) error on card {cid}: {e}")
                self._handle_card_failure(cid, provider)

            time.sleep(1.5)

        if provider in self.active_threads_status:
            try:
                del self.active_threads_status[provider]
            except: pass
        logger.info(f"AI-Hints Thread for {provider} stopped.")

# Global instance singleton
batch_manager = BatchManager()

def initialize_batch_manager():
    """Call on addon setup to resume outstanding polling or auto-resume local sequential queue if needed."""
    batch_manager.start_timer_if_needed()
    if batch_manager.local_queue and batch_manager.local_queue_active:
        logger.info("AI-Hints: Restoring interrupted local sequential queue on startup in a PAUSED state.")
        batch_manager.local_queue_paused = True
        batch_manager.local_queue_active = False # Allow the queue to start
        batch_manager.start_local_sequential_queue(None)
