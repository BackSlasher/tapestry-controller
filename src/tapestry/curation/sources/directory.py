"""Directory-based image source."""

import logging
import os
import random
from pathlib import Path
from typing import Iterator, List

import PIL.Image

from .base import ImageCandidate, Source

logger = logging.getLogger(__name__)

# Supported image extensions
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".webp"}


class DirectorySource(Source):
    """Source that reads images from a local directory."""

    is_local = True

    def __init__(self, path: str, shuffle: bool = True, recursive: bool = False):
        """Initialize directory source.

        Args:
            path: Path to directory (supports ~ expansion)
            shuffle: Whether to shuffle image order
            recursive: Whether to search subdirectories
        """
        self.path = Path(os.path.expanduser(path))
        self.shuffle = shuffle
        self.recursive = recursive
        self._skip_filters = True  # Can be overridden

    @property
    def name(self) -> str:
        return f"directory:{self.path}"

    def should_skip_filters(self) -> bool:
        return self._skip_filters

    def set_skip_filters(self, skip: bool) -> None:
        self._skip_filters = skip

    def _find_images(self) -> List[Path]:
        """Find all image files in directory."""
        if not self.path.exists():
            logger.warning(f"Directory does not exist: {self.path}")
            return []

        if not self.path.is_dir():
            logger.warning(f"Path is not a directory: {self.path}")
            return []

        images = []
        if self.recursive:
            for ext in IMAGE_EXTENSIONS:
                images.extend(self.path.rglob(f"*{ext}"))
                images.extend(self.path.rglob(f"*{ext.upper()}"))
        else:
            for ext in IMAGE_EXTENSIONS:
                images.extend(self.path.glob(f"*{ext}"))
                images.extend(self.path.glob(f"*{ext.upper()}"))

        return images

    def fetch(self) -> Iterator[ImageCandidate]:
        """Yield image candidates from directory."""
        images = self._find_images()

        if not images:
            logger.info(f"No images found in {self.path}")
            return

        if self.shuffle:
            random.shuffle(images)

        for image_path in images:
            try:
                img = PIL.Image.open(image_path)
                # Load into memory so file handle is released
                img.load()

                yield ImageCandidate(
                    image=img,
                    metadata={
                        "source_type": "directory",
                        "source_name": str(self.path),
                        "path": str(image_path),
                        "filename": image_path.name,
                        "title": image_path.stem,
                    },
                )
            except Exception as e:
                logger.warning(f"Failed to load image {image_path}: {e}")
                continue
