"""Keywords filter for curation pipeline."""

from typing import List, Optional

from ..sources.base import ImageCandidate
from .base import Filter, FilterResult


class KeywordsFilter(Filter):
    """Filter based on keywords in image title/metadata.

    Can be used to:
    - Exclude unwanted content (cars, sports, etc.)
    - Require certain topics (if keywords_include is set)
    """

    def __init__(
        self,
        keywords_exclude: Optional[List[str]] = None,
        keywords_include: Optional[List[str]] = None,
    ):
        """Initialize keywords filter.

        Args:
            keywords_exclude: Reject if title contains any of these (case-insensitive)
            keywords_include: Reject if title doesn't contain at least one of these
        """
        self.keywords_exclude = [k.lower() for k in (keywords_exclude or [])]
        self.keywords_include = [k.lower() for k in (keywords_include or [])]

    @property
    def name(self) -> str:
        parts = []
        if self.keywords_exclude:
            parts.append(f"exclude={self.keywords_exclude}")
        if self.keywords_include:
            parts.append(f"include={self.keywords_include}")
        return f"keywords({', '.join(parts)})"

    def check(self, candidate: ImageCandidate) -> FilterResult:
        """Check if image title/metadata passes keyword filters."""
        # Get searchable text from metadata
        title = candidate.title.lower()
        source_name = candidate.metadata.get("source_name", "").lower()
        searchable = f"{title} {source_name}"

        # Check exclude list
        for keyword in self.keywords_exclude:
            if keyword in searchable:
                return FilterResult.reject(f"Contains excluded keyword: '{keyword}'")

        # Check include list (if specified, must match at least one)
        if self.keywords_include:
            if not any(keyword in searchable for keyword in self.keywords_include):
                return FilterResult.reject(
                    f"Does not contain any required keyword: {self.keywords_include}"
                )

        return FilterResult.accept()
