"""New screensaver module that reads from curation staging."""

import logging
import threading
from typing import Callable, Optional

import PIL.Image

from ..curation import CurationManager

logger = logging.getLogger(__name__)


class ScreensaverV2:
    """Screensaver that reads from curated staging directory.

    This is the new simplified screensaver that:
    - Reads images from the staging directory (managed by CurationManager)
    - Walks through playlist.json in order (no random repeats)
    - Triggers curation if staging is empty
    """

    def __init__(
        self,
        curation_manager: CurationManager,
        image_sender: Callable[[PIL.Image.Image], None],
    ):
        """Initialize screensaver.

        Args:
            curation_manager: CurationManager instance for staging access
            image_sender: Callable that takes a PIL Image and sends it to displays
        """
        self.curation = curation_manager
        self.image_sender = image_sender

        self._thread: Optional[threading.Thread] = None
        self._stop_event: Optional[threading.Event] = None
        self._active = False
        self._interval = 300  # Default 5 minutes

    @property
    def is_active(self) -> bool:
        """Check if screensaver is currently active."""
        return self._active

    def start(self, interval: int = 300) -> None:
        """Start the screensaver.

        Args:
            interval: Seconds between image changes

        Raises:
            RuntimeError: If screensaver is already active
        """
        if self._active:
            raise RuntimeError("Screensaver is already active")

        self._interval = interval
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._active = True
        self._thread.start()

        logger.info(f"Screensaver started (interval: {interval}s)")

    def stop(self, timeout: float = 2.0) -> None:
        """Stop the screensaver.

        Args:
            timeout: Maximum time to wait for thread to stop
        """
        if not self._active:
            return

        if self._stop_event:
            self._stop_event.set()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

        self._active = False
        self._thread = None
        self._stop_event = None

        logger.info("Screensaver stopped")

    def next_image(self) -> bool:
        """Display the next image immediately.

        Returns:
            True if an image was successfully displayed
        """
        # Ensure staging has images
        if self.curation.staging.is_empty():
            logger.info("Staging empty, running curation...")
            result = self.curation.curate()
            if result.staged_count == 0:
                logger.warning("Curation produced no images")
                return False

        # Get next image
        image = self.curation.get_next_image()
        if image is None:
            logger.warning("No image available from staging")
            return False

        try:
            self.image_sender(image)
            logger.info("Displayed next image from staging")
            return True
        except Exception as e:
            logger.error(f"Failed to send image: {e}")
            return False

    def _worker(self) -> None:
        """Main screensaver worker thread."""
        # Ensure staging has images on startup
        if self.curation.staging.is_empty():
            logger.info("Staging empty on start, running curation...")
            try:
                self.curation.curate()
            except Exception as e:
                logger.error(f"Initial curation failed: {e}")

        while not self._stop_event.is_set():
            try:
                # Get next image from staging
                image = self.curation.get_next_image()

                if image is None:
                    # Staging might be empty, try to curate
                    logger.warning("No image from staging, attempting curation...")
                    try:
                        self.curation.curate()
                        image = self.curation.get_next_image()
                    except Exception as e:
                        logger.error(f"Curation failed: {e}")

                if image is not None:
                    self.image_sender(image)
                else:
                    logger.warning("Still no image available after curation")

            except Exception as e:
                logger.error(f"Screensaver error: {e}")

            # Wait for next cycle or stop signal
            self._stop_event.wait(self._interval)

    def get_status(self) -> dict:
        """Get screensaver status for API."""
        staging_info = self.curation.get_staging_info()
        return {
            "active": self._active,
            "interval": self._interval,
            "staging": staging_info,
        }
