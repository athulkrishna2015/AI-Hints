import os
import subprocess
import signal
import sys
import time
from .logger import logger

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

        if sys.platform == "win32":
            self.executable = os.path.join(self.bin_dir, "antigravity-proxy-windows.exe")
        elif sys.platform == "darwin":
            mac_suffix = "arm64" if is_arm else "x64"
            self.executable = os.path.join(self.bin_dir, f"antigravity-proxy-darwin-{mac_suffix}")
        else:
            # Default linux
            self.executable = os.path.join(self.bin_dir, "antigravity-proxy-linux")

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
            logger.info(f"Antigravity Proxy is already downloaded.")
            return True

        logger.info(f"Antigravity Proxy binary not found. Downloading...")
        try:
            import urllib.request
            import time
            start_time = time.time()
            
            binary_name = os.path.basename(self.executable)
            remote_url = f"https://github.com/athulkrishna2015/AI-Hints/releases/download/proxy-v0.7.0/{binary_name}"
            
            def _reporthook(count, block_size, total_size):
                if progress_callback:
                    downloaded = count * block_size
                    elapsed = time.time() - start_time
                    progress_callback(downloaded, total_size, elapsed)

            os.makedirs(self.bin_dir, exist_ok=True)
            urllib.request.urlretrieve(remote_url, self.executable, reporthook=_reporthook)
            logger.info(f"Successfully downloaded proxy to {self.executable}")
            # Ensure permissions right after download
            if sys.platform != "win32":
                os.chmod(self.executable, 0o755)
            return True
        except Exception as e:
            logger.error(f"Failed to download Antigravity Proxy: {e}")
            return False

    def start(self, config):
        """Launch the binary if enabled and not already running."""
        if not self.is_enabled(config):
            self.stop()
            return
            
        if self.process and self.process.poll() is None:
            logger.debug("Antigravity Proxy is already running.")
            return
            
        if not os.path.exists(self.executable):
            if not self.download_binary():
                return
            
        logger.info("Starting Antigravity Proxy daemon...")
        
        # Ensure executable permissions in case of fallback
        if sys.platform != "win32":
            os.chmod(self.executable, 0o755)
            
        env = os.environ.copy()
        env["PORT"] = "3015"
        
        try:
            # We use creationflags/preexec_fn to detach the process slightly 
            # so it doesn't die ungracefully if Anki crashes, though we still track it
            kwargs = {}
            if sys.platform == "win32":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            
            self.process = subprocess.Popen(
                [self.executable],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=self.bin_dir,
                **kwargs
            )
            logger.info(f"Antigravity Proxy daemon started (PID: {self.process.pid}) on port 3015.")
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
