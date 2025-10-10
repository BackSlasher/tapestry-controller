import hashlib
import io
from typing import Optional, Tuple

import PIL.Image


class ImageCache:
    """Handles caching of processed images for web serving with PNG conversion and ETag generation."""

    def __init__(self):
        self._cached_image: Optional[PIL.Image.Image] = None
        self._cached_png_bytes: Optional[bytes] = None
        self._cached_etag: Optional[str] = None

    def update_image(self, image: PIL.Image.Image) -> None:
        """Update the cached image and recompute PNG bytes and ETag."""
        self._cached_image = image.copy()

        # Convert to PNG bytes
        img_buffer = io.BytesIO()
        image.save(img_buffer, format="PNG")
        self._cached_png_bytes = img_buffer.getvalue()

        # Generate ETag from PNG bytes
        md5_hash = hashlib.md5(self._cached_png_bytes).hexdigest()
        self._cached_etag = f'"{md5_hash}"'

    def get_image(self) -> Optional[PIL.Image.Image]:
        """Get the cached PIL image."""
        return self._cached_image

    def get_png_data(self, image: PIL.Image.Image) -> Tuple[Optional[bytes], Optional[str]]:
        """Get PNG bytes and ETag for the given image.

        If the image matches the cached one, returns cached data.
        If different or no cache, recalculates and caches the result.

        Args:
            image: The PIL Image to get PNG data for

        Returns: (png_bytes, etag) or (None, None) if image is None
        """
        if image is None:
            return None, None

        # Check if we need to update the cache
        if not self._images_equal(image, self._cached_image):
            self.update_image(image)

        return self._cached_png_bytes, self._cached_etag

    def _images_equal(self, img1: Optional[PIL.Image.Image], img2: Optional[PIL.Image.Image]) -> bool:
        """Check if two images are equal."""
        if img1 is None or img2 is None:
            return img1 is img2
        if img1.size != img2.size or img1.mode != img2.mode:
            return False
        return img1.tobytes() == img2.tobytes()

    def clear(self) -> None:
        """Clear all cached data."""
        self._cached_image = None
        self._cached_png_bytes = None
        self._cached_etag = None