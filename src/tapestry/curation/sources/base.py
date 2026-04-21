"""Base classes for curation sources."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Optional

import PIL.Image


@dataclass
class ImageCandidate:
    """An image candidate from a source, ready for filtering."""

    image: PIL.Image.Image
    metadata: dict = field(default_factory=dict)

    # Common metadata keys:
    # - source_type: "directory", "collection", "reddit", etc.
    # - source_name: specific source identifier
    # - title: image title (for reddit posts, etc.)
    # - url: source URL if from web
    # - path: local path if from filesystem
    # - filename: original filename

    @property
    def source_type(self) -> str:
        return self.metadata.get("source_type", "unknown")

    @property
    def title(self) -> str:
        return self.metadata.get("title", "")

    @property
    def filename(self) -> str:
        return self.metadata.get("filename", "image.png")

    def width(self) -> int:
        return self.image.size[0]

    def height(self) -> int:
        return self.image.size[1]


@dataclass
class SourceConfig:
    """Base configuration for a source."""

    type: str
    skip_filters: Optional[bool] = None  # None = use default for source type

    def should_skip_filters(self, is_local: bool) -> bool:
        """Determine if filters should be skipped.

        Args:
            is_local: Whether this is a local source (directory/collection)

        Returns:
            True if filters should be skipped
        """
        if self.skip_filters is not None:
            return self.skip_filters
        # Default: local sources skip filters, remote sources apply filters
        return is_local


class Source(ABC):
    """Abstract base class for image sources."""

    # Whether this is a local source (affects default filter behavior)
    is_local: bool = False

    @abstractmethod
    def fetch(self) -> Iterator[ImageCandidate]:
        """Yield image candidates one at a time.

        Memory-friendly: loads and yields one image at a time.
        Caller is responsible for closing/discarding images after use.

        Yields:
            ImageCandidate objects
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name for this source."""
        ...

    def should_skip_filters(self) -> bool:
        """Whether filters should be skipped for this source."""
        # Subclasses can override, default based on is_local
        return self.is_local
