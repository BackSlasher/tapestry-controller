"""Unified process management for streaming subprocess output in Tapestry operations."""

import logging
import queue
import subprocess
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class StreamingProcess:
    """Represents a running process with streaming output capability."""

    def __init__(
        self,
        process_id: str,
        process: subprocess.Popen,
        operation_type: str,
        description: str,
    ):
        """Initialize a streaming process.

        Args:
            process_id: Unique identifier for the process
            process: The subprocess.Popen object
            operation_type: Type of operation (e.g., 'flash', 'ota_build')
            description: Human-readable description of the operation
        """
        self.process_id = process_id
        self.process = process
        self.operation_type = operation_type
        self.description = description
        self.output_queue = queue.Queue()
        self.finished = False
        self.return_code = None
        self.start_time = None
        self.end_time = None

    def is_running(self) -> bool:
        """Check if the process is still running."""
        return self.process.poll() is None and not self.finished


class ProcessManager:
    """Manages streaming processes for flash and OTA operations."""

    def __init__(self):
        """Initialize the process manager."""
        self.active_processes: Dict[str, StreamingProcess] = {}

    def start_process(
        self,
        cmd: List[str],
        cwd: str,
        operation_type: str,
        description: str,
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Start a new streaming process.

        Args:
            cmd: Command and arguments to execute
            cwd: Working directory for the process
            operation_type: Type of operation (e.g., 'flash', 'ota_build')
            description: Human-readable description
            timeout: Optional timeout in seconds

        Returns:
            Dict with start results including process_id
        """
        try:
            # Generate unique process ID
            process_id = str(uuid.uuid4())

            # Start the subprocess
            process = subprocess.Popen(
                cmd,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1,
            )

            # Create streaming process tracking object
            streaming_process = StreamingProcess(
                process_id, process, operation_type, description
            )
            self.active_processes[process_id] = streaming_process

            # Start output streaming thread
            output_thread = threading.Thread(
                target=self._stream_subprocess_output, args=(streaming_process,)
            )
            output_thread.daemon = True
            output_thread.start()

            logger.info(f"Started {operation_type} process {process_id}: {description}")

            return {
                "success": True,
                "process_id": process_id,
                "message": f"Started {description}",
                "operation_type": operation_type,
            }

        except Exception as e:
            error_msg = f"Failed to start {operation_type} process: {str(e)}"
            logger.error(error_msg)
            return {"success": False, "error": error_msg}

    def _stream_subprocess_output(self, streaming_process: StreamingProcess):
        """Stream subprocess output line by line."""
        import time

        streaming_process.start_time = time.time()

        try:
            while True:
                output = streaming_process.process.stdout.readline()  # ty: ignore
                if output == "" and streaming_process.process.poll() is not None:
                    break
                if output:
                    # Store output in process queue
                    streaming_process.output_queue.put(output.strip())

            # Process finished
            return_code = streaming_process.process.poll()
            streaming_process.finished = True
            streaming_process.return_code = return_code
            streaming_process.end_time = time.time()

            duration = streaming_process.end_time - streaming_process.start_time
            streaming_process.output_queue.put(
                f"Process finished with exit code: {return_code} (duration: {duration:.1f}s)"
            )

            logger.info(
                f"{streaming_process.operation_type.title()} process {streaming_process.process_id} "
                f"finished with exit code {return_code} after {duration:.1f}s"
            )

        except Exception as e:
            streaming_process.output_queue.put(f"Error streaming output: {e}")
            logger.error(
                f"Error streaming output for process {streaming_process.process_id}: {e}"
            )

    def get_process(self, process_id: str) -> Optional[StreamingProcess]:
        """Get a streaming process by ID.

        Args:
            process_id: The process ID

        Returns:
            StreamingProcess object or None if not found
        """
        return self.active_processes.get(process_id)

    def stop_process(self, process_id: str) -> Dict[str, Any]:
        """Stop a running process.

        Args:
            process_id: The process ID to stop

        Returns:
            Dict with stop results
        """
        if process_id not in self.active_processes:
            return {"success": False, "error": "Process not found"}

        try:
            streaming_process = self.active_processes[process_id]
            process = streaming_process.process

            if process.poll() is None:  # Process is still running
                process.terminate()
                # Wait a bit for graceful termination
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()  # Force kill if it doesn't terminate

            # Mark as finished
            streaming_process.finished = True
            streaming_process.return_code = process.returncode
            streaming_process.output_queue.put("Process terminated by user")

            logger.info(
                f"{streaming_process.operation_type.title()} process {process_id} stopped"
            )
            return {
                "success": True,
                "message": f"{streaming_process.operation_type.title()} process stopped",
            }

        except Exception as e:
            error_msg = f"Failed to stop process: {str(e)}"
            logger.error(f"Error stopping process {process_id}: {e}")
            return {"success": False, "error": error_msg}

    def get_active_processes(
        self, operation_type: Optional[str] = None
    ) -> List[StreamingProcess]:
        """Get all active processes, optionally filtered by operation type.

        Args:
            operation_type: Optional filter by operation type

        Returns:
            List of active StreamingProcess objects
        """
        processes = [sp for sp in self.active_processes.values() if not sp.finished]

        if operation_type:
            processes = [sp for sp in processes if sp.operation_type == operation_type]

        return processes

    def get_process_count(self, operation_type: Optional[str] = None) -> int:
        """Get the number of active processes.

        Args:
            operation_type: Optional filter by operation type

        Returns:
            Number of active processes
        """
        return len(self.get_active_processes(operation_type))

    def cleanup_finished_processes(self, max_age_seconds: int = 3600):
        """Clean up old finished processes to prevent memory leaks.

        Args:
            max_age_seconds: Maximum age in seconds for finished processes to keep
        """
        import time

        current_time = time.time()
        to_remove = []

        for process_id, sp in self.active_processes.items():
            if sp.finished and sp.output_queue.empty():
                # Remove if older than max_age_seconds
                if sp.end_time and (current_time - sp.end_time) > max_age_seconds:
                    to_remove.append(process_id)

        for process_id in to_remove:
            del self.active_processes[process_id]
            logger.debug(f"Cleaned up finished process {process_id}")

    def get_process_info(self, process_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a process.

        Args:
            process_id: The process ID

        Returns:
            Dict with process information or None if not found
        """
        streaming_process = self.active_processes.get(process_id)
        if not streaming_process:
            return None

        duration = None
        if streaming_process.start_time:
            end_time = streaming_process.end_time or time.time()
            duration = end_time - streaming_process.start_time

        return {
            "process_id": streaming_process.process_id,
            "operation_type": streaming_process.operation_type,
            "description": streaming_process.description,
            "finished": streaming_process.finished,
            "return_code": streaming_process.return_code,
            "pid": (
                streaming_process.process.pid
                if streaming_process.process.poll() is None
                else None
            ),
            "duration": duration,
            "start_time": streaming_process.start_time,
            "end_time": streaming_process.end_time,
        }

    def get_all_process_info(self) -> Dict[str, Dict[str, Any]]:
        """Get information about all processes.

        Returns:
            Dict mapping process_id to process information
        """
        return {
            process_id: self.get_process_info(process_id)
            for process_id in self.active_processes.keys()
        }
