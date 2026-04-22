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


class SeamFilter(Filter):
    """Filter that rejects images with complex content at panel seam lines.

    Multi-panel e-ink displays have visible seams between panels. Images with
    high-detail content (faces, text, complex edges) crossing the seam look
    bad. This filter analyzes edge density in a narrow band at the seam line
    and rejects images where it's too high.

    Uses two metrics:
    - Mean edge density: catches busy/complex areas
    - Max row gradient: catches hard horizontal lines (composites, borders)
    """

    def __init__(
        self,
        seam_position: float = 0.5,
        band_percent: float = 0.05,
        max_edge_density: float = 0.15,
        max_hard_edge: float = 0.25,
    ):
        """Initialize seam filter.

        Args:
            seam_position: Vertical position of seam (0-1). 0.5 = middle.
            band_percent: Height of band to analyze as fraction of image (0.05 = 5%).
            max_edge_density: Maximum mean edge density (0-1). Lower = stricter.
            max_hard_edge: Maximum single-row gradient (0-1). Catches hard
                          horizontal lines like composite boundaries.
        """
        self.seam_position = seam_position
        self.band_percent = band_percent
        self.max_edge_density = max_edge_density
        self.max_hard_edge = max_hard_edge

    @property
    def name(self) -> str:
        return f"seam(pos={self.seam_position}, max_edges={self.max_edge_density})"

    def check(self, candidate: ImageCandidate) -> FilterResult:
        """Check if image has low edge density at the seam line."""
        img = candidate.image
        height = img.height

        # Calculate band boundaries
        band_height = int(height * self.band_percent)
        seam_y = int(height * self.seam_position)
        y_start = max(0, seam_y - band_height // 2)
        y_end = min(height, seam_y + band_height // 2)

        if y_end <= y_start:
            return FilterResult.accept()

        # Convert to grayscale and extract band
        gray = img.convert("L")
        band = np.array(gray)[y_start:y_end, :]

        # Calculate vertical gradient (edges crossing the seam)
        if band.shape[0] < 2:
            return FilterResult.accept()

        # Simple gradient: difference between adjacent rows
        gradient = np.abs(np.diff(band.astype(np.float32), axis=0))

        # Mean edge density (catches busy areas)
        edge_density = np.mean(gradient) / 255.0

        # Max row gradient (catches hard horizontal lines like composites)
        row_means = np.mean(gradient, axis=1) / 255.0
        max_row_gradient = np.max(row_means)

        if edge_density > self.max_edge_density:
            return FilterResult.reject(
                f"Seam edge density {edge_density:.1%} exceeds maximum {self.max_edge_density:.0%}"
            )

        if max_row_gradient > self.max_hard_edge:
            return FilterResult.reject(
                f"Hard edge at seam {max_row_gradient:.1%} exceeds maximum {self.max_hard_edge:.0%}"
            )

        return FilterResult.accept()
