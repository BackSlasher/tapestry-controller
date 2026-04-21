"""Curation manager - background thread and orchestration."""

import logging
import threading
from typing import Callable, List, Optional

from .filters import ContrastFilter, Filter, KeywordsFilter, ResolutionFilter
from .filters.contrast import HistogramFilter
from .pipeline import CurationPipeline, CurationResult
from .sources import CollectionSource, RedditSource, Source
from .staging import StagingManager

logger = logging.getLogger(__name__)


class CurationManager:
    """Manages curation with background thread and timer.

    Responsibilities:
    - Run curation on a schedule (background thread)
    - Run curation on-demand (manual trigger)
    - Auto-curate when staging is empty
    - Build sources and filters from config
    """

    def __init__(
        self,
        staging_path: str = ".tapestry-data/staging",
        curation_interval: int = 86400,  # 24 hours default
    ):
        """Initialize curation manager.

        Args:
            staging_path: Path to staging directory
            curation_interval: Seconds between auto-curations
        """
        self.staging = StagingManager(staging_path)
        self.curation_interval = curation_interval

        self._thread: Optional[threading.Thread] = None
        self._stop_event: Optional[threading.Event] = None
        self._active = False

        # Config (set via configure())
        self._local_sources: List[Source] = []
        self._remote_sources: List[Source] = []
        self._filters: List[Filter] = []
        self._filters_enabled = True
        self._target_count = 20
        self._shuffle = True

        # Callback for when curation completes
        self._on_curation_complete: Optional[Callable[[CurationResult], None]] = None

    @property
    def is_active(self) -> bool:
        """Check if background curation is running."""
        return self._active

    def configure(
        self,
        local_sources: Optional[List[Source]] = None,
        remote_sources: Optional[List[Source]] = None,
        filters: Optional[List[Filter]] = None,
        filters_enabled: bool = True,
        target_count: int = 20,
        shuffle: bool = True,
        curation_interval: int = 86400,
        on_complete: Optional[Callable[[CurationResult], None]] = None,
    ) -> None:
        """Configure the curation manager.

        Args:
            local_sources: List of local sources (directories, collections)
            remote_sources: List of remote sources (reddit, etc.)
            filters: List of filters to apply
            filters_enabled: Master switch for filters
            target_count: Number of images to stage
            shuffle: Whether to shuffle the final playlist
            curation_interval: Seconds between auto-curations
            on_complete: Callback when curation completes
        """
        self._local_sources = local_sources or []
        self._remote_sources = remote_sources or []
        self._filters = filters or []
        self._filters_enabled = filters_enabled
        self._target_count = target_count
        self._shuffle = shuffle
        self.curation_interval = curation_interval
        self._on_curation_complete = on_complete

    def configure_from_dict(self, config: dict) -> None:
        """Configure from a dictionary (e.g., from settings).

        Expected config structure:
        {
            "staging_path": ".tapestry-data/staging",
            "count": 20,
            "shuffle": True,
            "interval": 86400,
            "filters": {
                "enabled": True,
                "min_width": 1920,
                "min_height": 1080,
                "min_contrast": 150,
                "keywords_exclude": ["car", "sports"],
            },
            "sources": [
                {"type": "collection", "name": "favorites"},
                {"type": "reddit", "subreddits": ["ImaginaryFallout"], ...},
            ]
        }
        """
        # Update staging path if provided
        if "staging_path" in config:
            self.staging = StagingManager(config["staging_path"])

        # Build filters
        filters = []
        filter_config = config.get("filters", {})
        if filter_config.get("enabled", True):
            if "min_width" in filter_config or "min_height" in filter_config:
                filters.append(ResolutionFilter(
                    min_width=filter_config.get("min_width", 1920),
                    min_height=filter_config.get("min_height", 1080),
                ))
            if "min_contrast" in filter_config:
                filters.append(ContrastFilter(
                    min_contrast=filter_config.get("min_contrast", 150),
                ))
            min_entropy = filter_config.get("min_histogram_entropy")
            if min_entropy is not None:
                filters.append(HistogramFilter(
                    min_entropy=min_entropy,
                ))
            if "keywords_exclude" in filter_config or "keywords_include" in filter_config:
                filters.append(KeywordsFilter(
                    keywords_exclude=filter_config.get("keywords_exclude", []),
                    keywords_include=filter_config.get("keywords_include", []),
                ))

        # Build sources
        local_sources = []
        remote_sources = []
        collections_dir = config.get("collections_dir", ".tapestry-data/collections")

        for source_config in config.get("sources", []):
            source_type = source_config.get("type")

            if source_type == "collection":
                source = CollectionSource(
                    collection_name=source_config["name"],
                    collections_dir=collections_dir,
                    shuffle=source_config.get("shuffle", True),
                )
                if "skip_filters" in source_config:
                    source.set_skip_filters(source_config["skip_filters"])
                local_sources.append(source)

            elif source_type == "reddit":
                source = RedditSource(
                    subreddits=source_config.get("subreddits", []),
                    sort=source_config.get("sort", "top"),
                    time_period=source_config.get("time_period", "week"),
                    limit=source_config.get("limit", 30),
                    keywords_include=source_config.get("keywords_include"),
                    keywords_exclude=source_config.get("keywords_exclude"),
                    shuffle=source_config.get("shuffle", True),
                )
                if "skip_filters" in source_config:
                    source.set_skip_filters(source_config["skip_filters"])
                remote_sources.append(source)

        self.configure(
            local_sources=local_sources,
            remote_sources=remote_sources,
            filters=filters,
            filters_enabled=filter_config.get("enabled", True),
            target_count=config.get("count", 20),
            shuffle=config.get("shuffle", True),
            curation_interval=config.get("interval", 86400),
        )

    def curate(self, dry_run: bool = False) -> CurationResult:
        """Run curation immediately.

        Args:
            dry_run: If True, don't actually stage images

        Returns:
            CurationResult with statistics
        """
        logger.info("Starting curation...")

        pipeline = CurationPipeline(
            staging=self.staging,
            filters=self._filters,
            filters_enabled=self._filters_enabled,
            target_count=self._target_count,
            shuffle=self._shuffle,
        )

        result = pipeline.run(
            local_sources=self._local_sources,
            remote_sources=self._remote_sources,
            dry_run=dry_run,
        )

        if self._on_curation_complete and not dry_run:
            self._on_curation_complete(result)

        return result

    def curate_if_empty(self) -> Optional[CurationResult]:
        """Run curation only if staging is empty.

        Returns:
            CurationResult if curation was run, None otherwise
        """
        if self.staging.is_empty():
            logger.info("Staging is empty, running curation...")
            return self.curate()
        return None

    def start(self) -> None:
        """Start background curation thread."""
        if self._active:
            logger.warning("Curation manager already active")
            return

        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._active = True
        self._thread.start()

        logger.info(f"Curation manager started (interval: {self.curation_interval}s)")

    def stop(self, timeout: float = 5.0) -> None:
        """Stop background curation thread."""
        if not self._active:
            return

        if self._stop_event:
            self._stop_event.set()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

        self._active = False
        self._thread = None
        self._stop_event = None

        logger.info("Curation manager stopped")

    def _worker(self) -> None:
        """Background worker thread."""
        # Initial curation if staging is empty
        if self.staging.is_empty():
            try:
                self.curate()
            except Exception as e:
                logger.error(f"Initial curation failed: {e}")

        # Periodic curation
        while not self._stop_event.is_set():
            # Wait for interval or stop signal
            if self._stop_event.wait(self.curation_interval):
                break  # Stop signal received

            # Run curation
            try:
                self.curate()
            except Exception as e:
                logger.error(f"Periodic curation failed: {e}")

    def get_staging_info(self) -> dict:
        """Get staging information for status display."""
        return self.staging.get_info()

    def get_next_image(self):
        """Get next image from staging.

        Convenience method that delegates to staging manager.
        """
        return self.staging.get_next_image()
