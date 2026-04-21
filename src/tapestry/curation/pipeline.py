"""Curation pipeline - orchestrates sources, filters, and staging."""

import logging
from dataclasses import dataclass, field
from typing import List, Optional

from .filters.base import Filter
from .sources.base import ImageCandidate, Source
from .staging import StagingManager

logger = logging.getLogger(__name__)


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
    ) -> CurationResult:
        """Run the curation pipeline.

        Args:
            local_sources: Local sources (directories, collections)
            remote_sources: Remote sources (reddit, etc.)
            dry_run: If True, don't actually stage images

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

        # Phase 1: Process local sources (skip filters by default)
        logger.info("Phase 1: Processing local sources...")
        for source in local_sources:
            if staged_count >= self.target_count:
                break

            source_stats = {"candidates": 0, "staged": 0, "filtered": 0}
            skip_filters = source.should_skip_filters()

            logger.info(f"Processing source: {source.name} (skip_filters={skip_filters})")

            for candidate in source.fetch():
                if staged_count >= self.target_count:
                    break

                result.total_candidates += 1
                source_stats["candidates"] += 1

                # Apply filters if not skipped
                if self.filters_enabled and not skip_filters:
                    passed, reason = self._apply_filters(candidate)
                    if not passed:
                        logger.debug(f"Filtered: {candidate.title} - {reason}")
                        result.filtered_count += 1
                        source_stats["filtered"] += 1
                        continue

                # Stage the image
                if not dry_run:
                    filename = self.staging.add_image(candidate, staged_count)
                    staged_filenames.append(filename)

                staged_count += 1
                source_stats["staged"] += 1
                logger.info(f"Staged: {candidate.title} from {source.name}")

            result.sources_summary[source.name] = source_stats

        # Phase 2: Process remote sources (apply filters by default)
        if staged_count < self.target_count:
            logger.info("Phase 2: Processing remote sources...")
            for source in remote_sources:
                if staged_count >= self.target_count:
                    break

                source_stats = {"candidates": 0, "staged": 0, "filtered": 0}
                skip_filters = source.should_skip_filters()

                logger.info(f"Processing source: {source.name} (skip_filters={skip_filters})")

                for candidate in source.fetch():
                    if staged_count >= self.target_count:
                        break

                    result.total_candidates += 1
                    source_stats["candidates"] += 1

                    # Apply filters if not skipped
                    if self.filters_enabled and not skip_filters:
                        passed, reason = self._apply_filters(candidate)
                        if not passed:
                            logger.debug(f"Filtered: {candidate.title} - {reason}")
                            result.filtered_count += 1
                            source_stats["filtered"] += 1
                            continue

                    # Stage the image
                    if not dry_run:
                        filename = self.staging.add_image(candidate, staged_count)
                        staged_filenames.append(filename)

                    staged_count += 1
                    source_stats["staged"] += 1
                    logger.info(f"Staged: {candidate.title} from {source.name}")

                result.sources_summary[source.name] = source_stats

        result.staged_count = staged_count

        # Write playlist
        if not dry_run and staged_filenames:
            self.staging.write_playlist(staged_filenames, shuffle=self.shuffle)

        logger.info(
            f"Curation complete: {result.staged_count} staged, "
            f"{result.filtered_count} filtered, {result.total_candidates} total candidates"
        )

        return result
