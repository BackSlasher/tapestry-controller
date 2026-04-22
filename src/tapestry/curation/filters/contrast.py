"""Contrast filter for curation pipeline."""

import numpy as np

from ..sources.base import ImageCandidate
from .base import Filter, FilterResult


class ContrastFilter(Filter):
    """Filter that rejects low-contrast images.

    E-ink displays have limited grayscale levels (typically 16 for 4-bit).
    Low contrast images look washed out and lack detail on e-ink.

    This filter converts to grayscale and checks the range of pixel values.
    """

    def __init__(self, min_contrast: int = 150):
        """Initialize contrast filter.

        Args:
            min_contrast: Minimum contrast (max_pixel - min_pixel) on 0-255 scale.
                         150 is a reasonable default - rejects very flat/hazy images
                         while accepting most normal photos.
        """
        self.min_contrast = min_contrast

    @property
    def name(self) -> str:
        return f"contrast(min={self.min_contrast})"

    def check(self, candidate: ImageCandidate) -> FilterResult:
        """Check if image has sufficient contrast for e-ink display."""
        # Convert to grayscale
        gray = candidate.image.convert("L")

        # Get pixel data as numpy array
        pixels = np.array(gray)

        # Calculate contrast as range of pixel values
        min_val = int(pixels.min())
        max_val = int(pixels.max())
        contrast = max_val - min_val

        if contrast >= self.min_contrast:
            return FilterResult.accept()

        return FilterResult.reject(
            f"Contrast {contrast} (range {min_val}-{max_val}) below minimum {self.min_contrast}"
        )


class HistogramFilter(Filter):
    """Filter that rejects images with poorly distributed histograms.

    Images that look good on e-ink typically have pixels spread across
    the full grayscale range, not clustered in a narrow band.

    This filter uses histogram entropy as a measure of distribution.
    """

    def __init__(self, min_entropy: float = 4.0):
        """Initialize histogram filter.

        Args:
            min_entropy: Minimum histogram entropy (0-8 scale for 8-bit grayscale).
                        4.0 is a reasonable default - rejects very narrow histograms
                        while accepting most normal images.
        """
        self.min_entropy = min_entropy

    @property
    def name(self) -> str:
        return f"histogram(min_entropy={self.min_entropy})"

    def check(self, candidate: ImageCandidate) -> FilterResult:
        """Check if image has well-distributed histogram."""
        # Convert to grayscale
        gray = candidate.image.convert("L")

        # Get histogram (256 bins for 8-bit grayscale)
        histogram = gray.histogram()

        # Calculate entropy
        total = sum(histogram)
        if total == 0:
            return FilterResult.reject("Empty image")

        entropy = 0.0
        for count in histogram:
            if count > 0:
                p = count / total
                entropy -= p * np.log2(p)

        if entropy >= self.min_entropy:
            return FilterResult.accept()

        return FilterResult.reject(
            f"Histogram entropy {entropy:.2f} below minimum {self.min_entropy}"
        )


class AspectRatioFilter(Filter):
    """Filter that rejects images with poor aspect ratio fit.

    When an image's aspect ratio differs significantly from the target
    display layout, much of the image will be cropped. This filter
    calculates "coverage" - what percentage of the source image will
    actually be displayed.
    """

    def __init__(self, target_ratio: float, min_coverage: float = 0.6):
        """Initialize aspect ratio filter.

        Args:
            target_ratio: Target aspect ratio (width/height) of the display layout.
            min_coverage: Minimum coverage (0-1). 0.6 means at least 60% of
                         the source image must be visible after fitting.
        """
        self.target_ratio = target_ratio
        self.min_coverage = min_coverage

    @property
    def name(self) -> str:
        return f"aspect_ratio(target={self.target_ratio:.2f}, min_coverage={self.min_coverage})"

    def check(self, candidate: ImageCandidate) -> FilterResult:
        """Check if image aspect ratio fits the target layout."""
        img = candidate.image
        src_ratio = img.width / img.height

        # Coverage is how much of the source image will be visible
        # after fitting to the target aspect ratio
        coverage = min(src_ratio, self.target_ratio) / max(src_ratio, self.target_ratio)

        if coverage >= self.min_coverage:
            return FilterResult.accept()

        return FilterResult.reject(
            f"Aspect ratio {src_ratio:.2f} gives {coverage:.0%} coverage "
            f"(target ratio {self.target_ratio:.2f}, min coverage {self.min_coverage:.0%})"
        )
