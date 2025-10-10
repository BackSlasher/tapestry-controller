"""Device monitoring system for Tapestry devices."""

import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


@dataclass
class DeviceStatus:
    """Status information for a single device."""

    host: str
    online: bool = False
    last_seen: Optional[datetime] = None
    last_error: Optional[str] = None

    # Device info from /
    width: Optional[int] = None
    height: Optional[int] = None
    temperature: Optional[int] = None
    screen_model: Optional[str] = None

    # OTA info from /ota
    current_version: Optional[str] = None
    compile_date: Optional[str] = None
    compile_time: Optional[str] = None
    project_name: Optional[str] = None
    idf_version: Optional[str] = None
    running_partition: Optional[str] = None
    next_partition: Optional[str] = None
    app_elf_sha256: Optional[str] = None
    ota_state: Optional[str] = None
    rollback_enabled: Optional[bool] = None

    # Response times
    response_time_ms: Optional[float] = None


@dataclass
class MonitorConfig:
    """Configuration for device monitoring."""

    poll_interval: int = 30  # seconds
    request_timeout: int = 5  # seconds
    enabled: bool = True


class DeviceMonitor:
    """Monitors device status and stores information in memory."""

    def __init__(self, config: Optional[MonitorConfig] = None):
        """Initialize device monitor.

        Args:
            config: Monitoring configuration
        """
        self.config = config or MonitorConfig()
        self._device_statuses: Dict[str, DeviceStatus] = {}
        self._monitor_thread: Optional[threading.Thread] = None
        self._stop_event: Optional[threading.Event] = None
        self._running = False
        self._device_list: List[str] = []

    def start_monitoring(self, device_hosts: List[str]) -> None:
        """Start monitoring devices.

        Args:
            device_hosts: List of device IP addresses/hostnames to monitor
        """
        if self._running:
            logger.warning("Device monitoring is already running")
            return

        if not self.config.enabled:
            logger.info("Device monitoring is disabled")
            return

        self._device_list = device_hosts.copy()

        # Initialize device statuses
        for host in device_hosts:
            if host not in self._device_statuses:
                self._device_statuses[host] = DeviceStatus(host=host)

        # Start monitoring thread
        self._stop_event = threading.Event()
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._running = True
        self._monitor_thread.start()

        logger.info(
            f"Started monitoring {len(device_hosts)} devices (interval: {self.config.poll_interval}s)"
        )

    def stop_monitoring(self) -> None:
        """Stop device monitoring."""
        if not self._running:
            return

        self._running = False
        if self._stop_event:
            self._stop_event.set()

        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=2)

        logger.info("Device monitoring stopped")

    def get_device_status(self, host: str) -> Optional[DeviceStatus]:
        """Get status for a specific device.

        Args:
            host: Device IP address/hostname

        Returns:
            DeviceStatus or None if not found
        """
        return self._device_statuses.get(host)

    def get_all_statuses(self) -> Dict[str, DeviceStatus]:
        """Get status for all monitored devices.

        Returns:
            Dict mapping hostnames to DeviceStatus objects
        """
        return self._device_statuses.copy()

    def get_online_devices(self) -> List[DeviceStatus]:
        """Get list of online devices.

        Returns:
            List of DeviceStatus objects for online devices
        """
        return [status for status in self._device_statuses.values() if status.online]

    def get_offline_devices(self) -> List[DeviceStatus]:
        """Get list of offline devices.

        Returns:
            List of DeviceStatus objects for offline devices
        """
        return [
            status for status in self._device_statuses.values() if not status.online
        ]

    def update_device_list(self, device_hosts: List[str]) -> None:
        """Update the list of devices to monitor.

        Args:
            device_hosts: New list of device IP addresses/hostnames
        """
        self._device_list = device_hosts.copy()

        # Add new devices
        for host in device_hosts:
            if host not in self._device_statuses:
                self._device_statuses[host] = DeviceStatus(host=host)

        # Remove devices no longer in the list
        hosts_to_remove = [
            host for host in self._device_statuses.keys() if host not in device_hosts
        ]
        for host in hosts_to_remove:
            del self._device_statuses[host]

        logger.info(f"Updated device list: {len(device_hosts)} devices")

    def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        while not self._stop_event.wait(self.config.poll_interval):
            try:
                self._poll_all_devices()
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")

    def _poll_all_devices(self) -> None:
        """Poll all devices for status information."""
        for host in self._device_list:
            try:
                self._poll_device(host)
            except Exception as e:
                logger.error(f"Error polling device {host}: {e}")
                # Mark device as offline
                if host in self._device_statuses:
                    status = self._device_statuses[host]
                    status.online = False
                    status.last_error = str(e)

    def _poll_device(self, host: str) -> None:
        """Poll a single device for status information.

        Args:
            host: Device IP address/hostname
        """
        status = self._device_statuses.get(host)
        if not status:
            return

        start_time = time.time()

        try:
            # Get basic device info from /
            device_info = self._get_device_info(host)

            # Calculate response time
            response_time = (time.time() - start_time) * 1000  # ms

            # Update status with device info
            status.online = True
            status.last_seen = datetime.now()
            status.last_error = None
            status.response_time_ms = response_time

            if device_info:
                status.width = device_info.get("width")
                status.height = device_info.get("height")
                status.temperature = device_info.get("temperature")
                status.screen_model = device_info.get("screen_model")

            # Get OTA info from /ota
            ota_info = self._get_ota_info(host)
            if ota_info:
                status.current_version = ota_info.get("current_version")
                status.compile_date = ota_info.get("compile_date")
                status.compile_time = ota_info.get("compile_time")
                status.project_name = ota_info.get("project_name")
                status.idf_version = ota_info.get("idf_version")
                status.running_partition = ota_info.get("running_partition")
                status.next_partition = ota_info.get("next_partition")
                status.app_elf_sha256 = ota_info.get("app_elf_sha256")
                status.ota_state = ota_info.get("ota_state")
                status.rollback_enabled = ota_info.get("rollback_enabled")

        except Exception as e:
            # Mark device as offline
            status.online = False
            status.last_error = str(e)
            status.response_time_ms = None
            logger.debug(f"Device {host} is offline: {e}")

    def _get_device_info(self, host: str) -> Optional[Dict]:
        """Get device information from / endpoint.

        Args:
            host: Device IP address/hostname

        Returns:
            Device info dict or None if failed
        """
        try:
            response = requests.get(
                f"http://{host}/", timeout=self.config.request_timeout
            )
            response.raise_for_status()
            return response.json()
        except Exception:
            return None

    def _get_ota_info(self, host: str) -> Optional[Dict]:
        """Get OTA information from /ota endpoint.

        Args:
            host: Device IP address/hostname

        Returns:
            OTA info dict or None if failed
        """
        try:
            response = requests.get(
                f"http://{host}/ota", timeout=self.config.request_timeout
            )
            response.raise_for_status()
            return response.json()
        except Exception:
            return None
