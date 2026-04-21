"""Base classes for curation filters."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from ..sources.base import ImageCandidate


@dataclass
class FilterResult:
    """Result of applying a filter to an image candidate."""

    passed: bool
    reason: Optional[str] = None  # Human-readable reason if rejected

    @classmethod
    def accept(cls) -> "FilterResult":
        return cls(passed=True)

    @classmethod
    def reject(cls, reason: str) -> "FilterResult":
        return cls(passed=False, reason=reason)


class Filter(ABC):
    """Abstract base class for image filters."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name for this filter."""
        ...

    @abstractmethod
    def check(self, candidate: ImageCandidate) -> FilterResult:
        """Check if an image candidate passes this filter.

        Args:
            candidate: The image candidate to check

        Returns:
            FilterResult indicating pass/fail and reason
        """
        ...
