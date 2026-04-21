"""Collection-based image source."""

import logging
import random
from pathlib import Path
from typing import Iterator, Optional

import PIL.Image

from .base import ImageCandidate, Source

logger = logging.getLogger(__name__)


class CollectionSource(Source):
    """Source that reads images from a Tapestry collection."""

    is_local = True

    def __init__(
        self,
        collection_name: str,
        collections_dir: str = ".tapestry-data/collections",
        shuffle: bool = True,
    ):
        """Initialize collection source.

        Args:
            collection_name: Name of the collection
            collections_dir: Root directory for collections
            shuffle: Whether to shuffle image order
        """
        self.collection_name = collection_name
        self.collections_dir = collections_dir
        self.shuffle = shuffle
        self._skip_filters = True  # Can be overridden

    @property
    def name(self) -> str:
        return f"collection:{self.collection_name}"

    def should_skip_filters(self) -> bool:
        return self._skip_filters

    def set_skip_filters(self, skip: bool) -> None:
        self._skip_filters = skip

    def _get_collection_path(self) -> Optional[Path]:
        """Get the path to the collection."""
        # Import here to avoid circular imports
        from ...webui.collections_manager import get_collection_path

        return get_collection_path(self.collection_name, self.collections_dir)

    def _get_images(self) -> list[str]:
        """Get list of image files in the collection."""
        from ...webui.collections_manager import get_collection_images

        collection_path = self._get_collection_path()
        if not collection_path:
            return []
        return get_collection_images(collection_path)

    def fetch(self) -> Iterator[ImageCandidate]:
        """Yield image candidates from collection."""
        images = self._get_images()

        if not images:
            logger.info(f"No images found in collection '{self.collection_name}'")
            return

        if self.shuffle:
            random.shuffle(images)

        for image_path in images:
            try:
                path = Path(image_path)
                img = PIL.Image.open(path)
                # Load into memory so file handle is released
                img.load()

                yield ImageCandidate(
                    image=img,
                    metadata={
                        "source_type": "collection",
                        "source_name": self.collection_name,
                        "path": str(path),
                        "filename": path.name,
                        "title": path.stem,
                    },
                )
            except Exception as e:
                logger.warning(f"Failed to load image {image_path}: {e}")
                continue
