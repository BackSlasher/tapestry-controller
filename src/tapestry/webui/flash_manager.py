"""Flash firmware management for Tapestry devices."""

import logging
import os
import queue
import subprocess
import threading
import uuid
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Default node directory path
DEFAULT_NODE_DIRECTORY = os.path.expanduser("~/node/")


class FlashProcess:
    """Represents a running flash process."""

    def __init__(self, process_id: str, process: subprocess.Popen, screen_type: str):
        self.process_id = process_id
        self.process = process
        self.screen_type = screen_type
        self.output_queue = queue.Queue()
        self.finished = False
        self.return_code = None


class FlashManager:
    """Manages firmware flashing for Tapestry devices."""

    def __init__(self, node_directory: Optional[str] = None):
        """Initialize Flash manager.

        Args:
            node_directory: Path to the node directory. If None, auto-detected.
        """
        if node_directory is None:
            node_directory = DEFAULT_NODE_DIRECTORY

        self.node_dir = node_directory
        self.setup_script = os.path.join(self.node_dir, "setup.sh")
        self.active_processes: Dict[str, FlashProcess] = {}

    def validate_environment(self) -> Dict[str, Any]:
        """Validate that the flash environment is set up correctly.

        Returns:
            Dict with validation results
        """
        issues = []

        if not os.path.exists(self.node_dir):
            issues.append(f"Node directory not found: {self.node_dir}")

        if not os.path.exists(self.setup_script):
            issues.append(f"Setup script not found: {self.setup_script}")

        if not os.access(self.setup_script, os.X_OK):
            issues.append(f"Setup script is not executable: {self.setup_script}")

        # Check if directory is a git repository
        git_dir = os.path.join(self.node_dir, ".git")
        if not os.path.exists(git_dir):
            issues.append(f"Node directory is not a git repository: {self.node_dir}")

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "node_dir": self.node_dir,
            "setup_script": self.setup_script,
        }

    def _update_git_repository(self) -> Dict[str, Any]:
        """Update the git repository before flashing.

        Returns:
            Dict with git update results
        """
        try:
            logger.info(f"Updating git repository in {self.node_dir}")
            git_result = subprocess.run(
                ["git", "pull"],
                cwd=self.node_dir,
                capture_output=True,
                text=True,
                timeout=60,  # 1 minute timeout for git pull
            )

            if git_result.returncode != 0:
                error_msg = f"Git pull failed (exit code {git_result.returncode}): {git_result.stderr.strip()}"
                logger.error(error_msg)
                return {
                    "success": False,
                    "error": error_msg,
                    "git_stdout": git_result.stdout,
                    "git_stderr": git_result.stderr,
                }

            logger.info(f"Git repository updated successfully for flash: {git_result.stdout.strip()}")
            return {
                "success": True,
                "git_stdout": git_result.stdout,
                "git_stderr": git_result.stderr,
            }

        except subprocess.TimeoutExpired:
            error_msg = "Git pull timeout - repository update took longer than 60 seconds"
            logger.error(error_msg)
            return {"success": False, "error": error_msg}
        except Exception as e:
            error_msg = f"Git pull error: {str(e)}"
            logger.error(f"Error updating git repository for flash: {e}")
            return {"success": False, "error": error_msg}

    def start_flash(self, screen_type: str) -> Dict[str, Any]:
        """Start the firmware flashing process.

        Args:
            screen_type: The screen type to flash

        Returns:
            Dict with start results including process_id
        """
        # Validate environment first
        validation = self.validate_environment()
        if not validation["valid"]:
            return {
                "success": False,
                "error": f"Environment validation failed: {'; '.join(validation['issues'])}",
            }

        # Update git repository
        git_result = self._update_git_repository()
        if not git_result["success"]:
            return git_result

        try:
            # Generate unique process ID
            process_id = str(uuid.uuid4())

            # Start the subprocess
            process = subprocess.Popen(
                [self.setup_script, screen_type],
                cwd=self.node_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1,
            )

            # Create flash process tracking object
            flash_process = FlashProcess(process_id, process, screen_type)
            self.active_processes[process_id] = flash_process

            # Start output streaming thread
            output_thread = threading.Thread(
                target=self._stream_subprocess_output,
                args=(flash_process,)
            )
            output_thread.daemon = True
            output_thread.start()

            logger.info(f"Started flashing {screen_type} firmware with process ID {process_id}")

            return {
                "success": True,
                "process_id": process_id,
                "message": f"Started flashing {screen_type} firmware",
                "git_stdout": git_result["git_stdout"],
                "git_stderr": git_result["git_stderr"],
            }

        except Exception as e:
            error_msg = f"Failed to start flash process: {str(e)}"
            logger.error(error_msg)
            return {"success": False, "error": error_msg}

    def _stream_subprocess_output(self, flash_process: FlashProcess):
        """Stream subprocess output line by line."""
        try:
            while True:
                output = flash_process.process.stdout.readline()
                if output == "" and flash_process.process.poll() is not None:
                    break
                if output:
                    # Store output in process queue
                    flash_process.output_queue.put(output.strip())

            # Process finished
            return_code = flash_process.process.poll()
            flash_process.finished = True
            flash_process.return_code = return_code
            flash_process.output_queue.put(
                f"Process finished with exit code: {return_code}"
            )
            logger.info(f"Flash process {flash_process.process_id} finished with exit code {return_code}")

        except Exception as e:
            flash_process.output_queue.put(f"Error streaming output: {e}")
            logger.error(f"Error streaming output for process {flash_process.process_id}: {e}")

    def get_process_output(self, process_id: str) -> Optional[FlashProcess]:
        """Get the flash process for output streaming.

        Args:
            process_id: The process ID

        Returns:
            FlashProcess object or None if not found
        """
        return self.active_processes.get(process_id)

    def stop_process(self, process_id: str) -> Dict[str, Any]:
        """Stop a running flash process.

        Args:
            process_id: The process ID to stop

        Returns:
            Dict with stop results
        """
        if process_id not in self.active_processes:
            return {"success": False, "error": "Process not found"}

        try:
            flash_process = self.active_processes[process_id]
            process = flash_process.process

            if process.poll() is None:  # Process is still running
                process.terminate()
                # Wait a bit for graceful termination
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()  # Force kill if it doesn't terminate

            # Mark as finished
            flash_process.finished = True
            flash_process.return_code = process.returncode
            flash_process.output_queue.put("Process terminated by user")

            logger.info(f"Flash process {process_id} stopped")
            return {"success": True, "message": "Flash process stopped"}

        except Exception as e:
            error_msg = f"Failed to stop process: {str(e)}"
            logger.error(f"Error stopping flash process {process_id}: {e}")
            return {"success": False, "error": error_msg}

    def cleanup_finished_processes(self):
        """Clean up finished processes to prevent memory leaks."""
        finished_processes = [
            pid for pid, fp in self.active_processes.items()
            if fp.finished and fp.output_queue.empty()
        ]

        for process_id in finished_processes:
            del self.active_processes[process_id]
            logger.debug(f"Cleaned up finished flash process {process_id}")

    def get_active_process_count(self) -> int:
        """Get the number of currently active flash processes."""
        return len([fp for fp in self.active_processes.values() if not fp.finished])

    def get_process_info(self, process_id: str) -> Optional[Dict[str, Any]]:
        """Get information about a flash process.

        Args:
            process_id: The process ID

        Returns:
            Dict with process information or None if not found
        """
        flash_process = self.active_processes.get(process_id)
        if not flash_process:
            return None

        return {
            "process_id": flash_process.process_id,
            "screen_type": flash_process.screen_type,
            "finished": flash_process.finished,
            "return_code": flash_process.return_code,
            "pid": flash_process.process.pid if flash_process.process.poll() is None else None,
        }