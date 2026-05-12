import os
import subprocess
import signal
import sys
import time
from .logger import logger

PROXY_VERSION = "proxy-v0.7.1"

class ProxyManager:
    def __init__(self):
        self.process = None
        
        # Determine paths
        addon_dir = os.path.dirname(os.path.abspath(__file__))
        self.bin_dir = os.path.join(addon_dir, "bin")
        
        # OS and Architecture detection
        import platform
        arch = platform.machine().lower()
        is_arm = "arm" in arch or "aarch" in arch

        # Explicit underlying release asset names
        if sys.platform == "win32":
            self.remote_asset = "antigravity-proxy-windows.exe"
        elif sys.platform == "darwin":
            mac_suffix = "arm64" if is_arm else "x64"
            self.remote_asset = f"antigravity-proxy-darwin-{mac_suffix}"
        else:
            self.remote_asset = "antigravity-proxy-linux"

        # Local filename now includes VERSION so that version bump updates trigger redownload automatically
        # e.g. antigravity-proxy-linux-v0.7.1
        local_name = f"{self.remote_asset}-{PROXY_VERSION}"
        self.executable = os.path.join(self.bin_dir, local_name)

    def is_enabled(self, config):
        """Check if the proxy should be running based on config."""
        ag_cfg = config.get("antigravity_proxy", {})
        if not isinstance(ag_cfg, dict):
            return False
        return ag_cfg.get("enabled", False)

    def download_binary(self, progress_callback=None):
        """Explicitly downloads the binary from GitHub if missing.
        progress_callback signature: (downloaded_bytes, total_bytes, elapsed_seconds)
        """
        if os.path.exists(self.executable):
            logger.info(f"Antigravity Proxy {PROXY_VERSION} is already downloaded.")
            return True

        logger.info(f"Antigravity Proxy {PROXY_VERSION} binary not found. Starting download...")
        try:
            import urllib.request
            import time
            start_time = time.time()
            
            remote_url = f"https://github.com/athulkrishna2015/AI-Hints/releases/download/{PROXY_VERSION}/{self.remote_asset}"
            
            def _reporthook(count, block_size, total_size):
                if progress_callback:
                    downloaded = count * block_size
                    elapsed = time.time() - start_time
                    progress_callback(downloaded, total_size, elapsed)

            os.makedirs(self.bin_dir, exist_ok=True)
            
            # Cleanup old version binaries to save disk space if user already had them
            try:
                for item in os.listdir(self.bin_dir):
                    if item.startswith("antigravity-proxy-") and item != os.path.basename(self.executable):
                        # Extra caution so we don't wipe database
                        if not item.endswith(".json"):
                            old_path = os.path.join(self.bin_dir, item)
                            if os.path.isfile(old_path):
                                os.remove(old_path)
                                logger.debug(f"Pruned legacy proxy binary: {item}")
            except: pass

            urllib.request.urlretrieve(remote_url, self.executable, reporthook=_reporthook)
            logger.info(f"Successfully downloaded proxy to {self.executable}")
            # Ensure permissions right after download with absolute authority
            if sys.platform != "win32":
                try:
                    os.chmod(self.executable, 0o755)
                    # Add shell fallback just in case of rigid mount drivers (NTFS/FUSE)
                    import subprocess
                    subprocess.run(["chmod", "+x", self.executable], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
                except: pass
            return True
        except Exception as e:
            logger.error(f"Failed to download Antigravity Proxy: {e}")
            return False

    def is_running(self):
        """Check if the daemon process is active."""
        return self.process is not None and self.process.poll() is None

    def start(self, config):
        """Launch the binary if enabled and not already running."""
        if not self.is_enabled(config):
            self.stop()
            return
            
        if self.process and self.process.poll() is None:
            logger.debug("Antigravity Proxy is already running.")
            return
            
        if not os.path.exists(self.executable):
            logger.warning("Antigravity Proxy binary is missing. Please click 'Fetch' in Add-on configuration to enable background daemon.")
            return
            
        logger.info("Starting Antigravity Proxy daemon...")
        
        # Ensure executable permissions right before launch ONLY if missing
        if sys.platform != "win32":
            if not os.access(self.executable, os.X_OK):
                try:
                    os.chmod(self.executable, 0o755)
                    # Force absolute authority shell call exactly like the user commands
                    import subprocess
                    subprocess.run(["chmod", "+x", self.executable], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
                except: pass
            
        env = os.environ.copy()
        env["PORT"] = "3000"
        
        try:
            # We use creationflags/preexec_fn to detach the process slightly 
            # so it doesn't die ungracefully if Anki crashes, though we still track it
            kwargs = {}
            if sys.platform == "win32":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            
            self.process = subprocess.Popen(
                [self.executable],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, # Merge stderr into stdout
                cwd=self.bin_dir,
                universal_newlines=True, # Read as text
                bufsize=1, # Line buffered
                **kwargs
            )
            
            # Spawn dynamic background reader to pipe process outputs into standard logs
            def _reader_thread():
                try:
                    for line in iter(self.process.stdout.readline, ""):
                        clean = line.strip()
                        if clean:
                            logger.info(f"[Proxy] {clean}")
                    self.process.stdout.close()
                except Exception as e:
                    logger.debug(f"Proxy log stream closed: {e}")
                    
            import threading
            threading.Thread(target=_reader_thread, daemon=True).start()
            
            logger.info(f"Antigravity Proxy daemon started (PID: {self.process.pid}) on port 3000.")
        except Exception as e:
            logger.error(f"Failed to start Antigravity Proxy: {e}")

    def stop(self):
        """Gracefully terminate the background binary."""
        if self.process and self.process.poll() is None:
            logger.info(f"Stopping Antigravity Proxy daemon (PID: {self.process.pid})...")
            try:
                if sys.platform == "win32":
                    self.process.terminate()
                else:
                    self.process.send_signal(signal.SIGTERM)
                
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                logger.warning("Proxy did not terminate gracefully, force killing...")
                self.process.kill()
            except Exception as e:
                logger.error(f"Error stopping proxy: {e}")
            finally:
                self.process = None

import atexit
proxy_manager = ProxyManager()
atexit.register(proxy_manager.stop)
