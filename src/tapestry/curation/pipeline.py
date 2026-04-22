"""Curation pipeline - orchestrates sources, filters, and staging."""

import logging
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from .filters.base import Filter
from .sources.base import ImageCandidate, Source
from .staging import StagingManager

logger = logging.getLogger(__name__)


@dataclass
class ProgressUpdate:
    """Progress update during curation."""

    phase: str  # "local" or "remote"
    source_index: int
    source_count: int
    source_name: str
    image_index: int
    image_total: int  # May be estimated
    staged_count: int
    filtered_count: int
    message: str


# Type alias for progress callback
ProgressCallback = Callable[[ProgressUpdate], None]


@dataclass
class CurationResult:
    """Result of running the curation pipeline."""

    staged_count: int
    total_candidates: int
    filtered_count: int
    sources_summary: dict = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)


class CurationPipeline:
    """Orchestrates the curation process: sources -> filters -> staging.

    The pipeline processes sources in two phases:
    1. Local sources (directories, collections) - skip filters by default
    2. Remote sources (reddit, etc.) - apply filters by default

    This gives priority to user-curated local content while filtering
    internet-sourced content for quality.
    """

    def __init__(
        self,
        staging: StagingManager,
        filters: Optional[List[Filter]] = None,
        filters_enabled: bool = True,
        target_count: int = 20,
        shuffle: bool = True,
    ):
        """Initialize curation pipeline.

        Args:
            staging: StagingManager instance
            filters: List of filters to apply
            filters_enabled: Master switch for filters
            target_count: Number of images to stage
            shuffle: Whether to shuffle the final playlist
        """
        self.staging = staging
        self.filters = filters or []
        self.filters_enabled = filters_enabled
        self.target_count = target_count
        self.shuffle = shuffle

    def _apply_filters(self, candidate: ImageCandidate) -> tuple[bool, Optional[str]]:
        """Apply all filters to a candidate.

        Returns:
            Tuple of (passed, rejection_reason)
        """
        for f in self.filters:
            result = f.check(candidate)
            if not result.passed:
                return False, f"{f.name}: {result.reason}"
        return True, None

    def run(
        self,
        local_sources: List[Source],
        remote_sources: List[Source],
        dry_run: bool = False,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> CurationResult:
        """Run the curation pipeline.

        Args:
            local_sources: Local sources (directories, collections)
            remote_sources: Remote sources (reddit, etc.)
            dry_run: If True, don't actually stage images
            progress_callback: Optional callback for progress updates

        Returns:
            CurationResult with statistics
        """
        result = CurationResult(
            staged_count=0,
            total_candidates=0,
            filtered_count=0,
            sources_summary={},
        )

        if not dry_run:
            self.staging.clear()

        staged_filenames = []
        staged_count = 0
        filtered_count = 0

        def send_progress(phase: str, source_idx: int, source_count: int,
                          source_name: str, img_idx: int, img_total: int, msg: str):
            if progress_callback:
                progress_callback(ProgressUpdate(
                    phase=phase,
                    source_index=source_idx,
                    source_count=source_count,
                    source_name=source_name,
                    image_index=img_idx,
                    image_total=img_total,
                    staged_count=staged_count,
                    filtered_count=filtered_count,
                    message=msg,
                ))

        all_sources = [(s, "local") for s in local_sources] + [(s, "remote") for s in remote_sources]
        total_sources = len(all_sources)

        for source_idx, (source, phase) in enumerate(all_sources):
            if staged_count >= self.target_count:
                break

            source_stats = {"candidates": 0, "staged": 0, "filtered": 0}
            skip_filters = source.should_skip_filters()

            send_progress(phase, source_idx + 1, total_sources, source.name, 0, 0,
                          f"Fetching from {source.name}...")

            logger.info(f"Processing source: {source.name} (skip_filters={skip_filters})")

            img_idx = 0
            for candidate in source.fetch():
                if staged_count >= self.target_count:
                    break

                img_idx += 1
                result.total_candidates += 1
                source_stats["candidates"] += 1

                send_progress(phase, source_idx + 1, total_sources, source.name,
                              img_idx, self.target_count, f"Processing image {img_idx}...")

                # Apply filters if enabled and not skipped for this source
                should_filter = self.filters_enabled and not skip_filters
                if should_filter:
                    passed, reason = self._apply_filters(candidate)
                    if not passed:
                        logger.debug(f"Filtered: {candidate.title} - {reason}")
                        result.filtered_count += 1
                        filtered_count += 1
                        source_stats["filtered"] += 1
                        continue

                # Stage the image
                if not dry_run:
                    filename = self.staging.add_image(candidate)
                    staged_filenames.append(filename)

                staged_count += 1
                source_stats["staged"] += 1
                logger.info(f"Staged: {candidate.title} from {source.name}")

            result.sources_summary[source.name] = source_stats

        result.staged_count = staged_count

        # Write playlist
        if not dry_run and staged_filenames:
            self.staging.write_playlist(staged_filenames, shuffle=self.shuffle)
            send_progress("done", total_sources, total_sources, "",
                          staged_count, staged_count, "Complete!")

        logger.info(
            f"Curation complete: {result.staged_count} staged, "
            f"{result.filtered_count} filtered, {result.total_candidates} total candidates"
        )

        return result
