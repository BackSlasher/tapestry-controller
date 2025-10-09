"""OTA (Over-The-Air) firmware update management for Tapestry devices."""

import logging
import os
import subprocess
from typing import Any, Dict, Optional

import requests
from requests.exceptions import ConnectionError, Timeout

logger = logging.getLogger(__name__)


class OTAManager:
    """Manages OTA firmware building and uploading for Tapestry devices."""

    def __init__(self, node_directory: Optional[str] = None):
        """Initialize OTA manager.

        Args:
            node_directory: Path to the node directory. If None, auto-detected.
        """
        if node_directory is None:
            node_directory = os.path.expanduser("~/node/")

        self.node_dir = node_directory
        self.build_script = os.path.join(self.node_dir, "build-ota.sh")
        self.firmware_path = os.path.join(self.node_dir, "build/tapestry-node.bin")

    def validate_environment(self) -> Dict[str, Any]:
        """Validate that the OTA environment is set up correctly.

        Returns:
            Dict with validation results
        """
        issues = []

        if not os.path.exists(self.node_dir):
            issues.append(f"Node directory not found: {self.node_dir}")

        if not os.path.exists(self.build_script):
            issues.append(f"Build script not found: {self.build_script}")

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "node_dir": self.node_dir,
            "build_script": self.build_script,
            "firmware_path": self.firmware_path,
        }

    def build_firmware(self, timeout: int = 300) -> Dict[str, Any]:
        """Build OTA firmware using the build script.

        Args:
            timeout: Build timeout in seconds (default: 5 minutes)

        Returns:
            Dict with build results
        """
        # Validate environment first
        validation = self.validate_environment()
        if not validation["valid"]:
            return {
                "success": False,
                "error": f"Environment validation failed: {'; '.join(validation['issues'])}",
            }

        try:
            # Make sure build script is executable
            os.chmod(self.build_script, 0o755)

            # Run build script
            logger.info(f"Building OTA firmware in {self.node_dir}")
            result = subprocess.run(
                ["./build-ota.sh"],
                cwd=self.node_dir,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            if result.returncode != 0:
                error_msg = f"Build failed (exit code {result.returncode}): {result.stderr.strip()}"
                logger.error(error_msg)
                return {
                    "success": False,
                    "error": error_msg,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                }

            # Check if firmware file was created
            if not os.path.exists(self.firmware_path):
                return {
                    "success": False,
                    "error": f"Firmware file not created: {self.firmware_path}",
                }

            # Get file size
            file_size = os.path.getsize(self.firmware_path)
            size_mb = round(file_size / (1024 * 1024), 2)

            logger.info(
                f"OTA firmware built successfully: {self.firmware_path} ({size_mb} MB)"
            )

            return {
                "success": True,
                "firmware_path": self.firmware_path,
                "size_bytes": file_size,
                "size_mb": size_mb,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }

        except subprocess.TimeoutExpired:
            error_msg = (
                f"Build timeout - firmware build took longer than {timeout} seconds"
            )
            logger.error(error_msg)
            return {"success": False, "error": error_msg}
        except Exception as e:
            error_msg = f"Build error: {str(e)}"
            logger.error(f"Error building OTA firmware: {e}")
            return {"success": False, "error": error_msg}

    def upload_firmware(
        self, device_ip: str, firmware_path: Optional[str] = None, timeout: int = 60
    ) -> Dict[str, Any]:
        """Upload firmware to device via OTA.

        Args:
            device_ip: IP address of the target device
            firmware_path: Path to firmware file. If None, uses default built firmware
            timeout: Upload timeout in seconds (default: 1 minute)

        Returns:
            Dict with upload results
        """
        if firmware_path is None:
            firmware_path = self.firmware_path

        # Validate inputs
        if not device_ip:
            return {"success": False, "error": "Device IP required"}

        if not os.path.exists(firmware_path):
            return {
                "success": False,
                "error": f"Firmware file not found: {firmware_path}",
            }

        try:
            # Get firmware size for logging
            file_size = os.path.getsize(firmware_path)
            size_mb = round(file_size / (1024 * 1024), 2)

            logger.info(f"Uploading OTA firmware to {device_ip} ({size_mb} MB)")

            # Upload firmware to device
            with open(firmware_path, "rb") as firmware_file:
                response = requests.post(
                    f"http://{device_ip}/ota",
                    data=firmware_file,
                    headers={"Content-Type": "application/octet-stream"},
                    timeout=timeout,
                )

            if response.status_code == 200:
                logger.info(f"OTA upload successful to {device_ip}")
                return {
                    "success": True,
                    "message": f"Firmware uploaded successfully to {device_ip}",
                    "device_ip": device_ip,
                    "size_mb": size_mb,
                    "response_text": response.text,
                }
            else:
                error_msg = (
                    f"Upload failed with HTTP {response.status_code}: {response.text}"
                )
                logger.error(error_msg)
                return {
                    "success": False,
                    "error": error_msg,
                    "status_code": response.status_code,
                    "response_text": response.text,
                }

        except Timeout:
            error_msg = f"Upload timeout - device {device_ip} did not respond within {timeout} seconds"
            logger.error(error_msg)
            return {"success": False, "error": error_msg}
        except ConnectionError:
            error_msg = f"Cannot connect to device {device_ip}"
            logger.error(error_msg)
            return {"success": False, "error": error_msg}
        except Exception as e:
            error_msg = f"Upload error: {str(e)}"
            logger.error(f"Error uploading OTA firmware to {device_ip}: {e}")
            return {"success": False, "error": error_msg}

    def get_firmware_info(self, firmware_path: Optional[str] = None) -> Dict[str, Any]:
        """Get information about a firmware file.

        Args:
            firmware_path: Path to firmware file. If None, uses default built firmware

        Returns:
            Dict with firmware information
        """
        if firmware_path is None:
            firmware_path = self.firmware_path

        if not os.path.exists(firmware_path):
            return {"exists": False, "path": firmware_path}

        try:
            stat = os.stat(firmware_path)
            file_size = stat.st_size
            size_mb = round(file_size / (1024 * 1024), 2)

            return {
                "exists": True,
                "path": firmware_path,
                "size_bytes": file_size,
                "size_mb": size_mb,
                "modified_time": stat.st_mtime,
            }
        except Exception as e:
            return {"exists": False, "path": firmware_path, "error": str(e)}

    def clean_build_artifacts(self) -> Dict[str, Any]:
        """Clean build artifacts and temporary files.

        Returns:
            Dict with cleanup results
        """
        cleaned_files = []
        errors = []

        # List of files/directories to clean
        targets = [
            self.firmware_path,
            os.path.join(self.node_dir, "build"),
        ]

        for target in targets:
            try:
                if os.path.isfile(target):
                    os.remove(target)
                    cleaned_files.append(target)
                elif os.path.isdir(target):
                    import shutil

                    shutil.rmtree(target)
                    cleaned_files.append(target)
            except Exception as e:
                errors.append(f"Failed to clean {target}: {str(e)}")

        return {
            "success": len(errors) == 0,
            "cleaned_files": cleaned_files,
            "errors": errors,
        }
