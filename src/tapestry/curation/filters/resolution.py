"""Resolution filter for curation pipeline."""

from ..sources.base import ImageCandidate
from .base import Filter, FilterResult


class ResolutionFilter(Filter):
    """Filter that rejects images below minimum resolution."""

    def __init__(self, min_width: int = 1920, min_height: int = 1080):
        """Initialize resolution filter.

        Args:
            min_width: Minimum acceptable width in pixels
            min_height: Minimum acceptable height in pixels
        """
        self.min_width = min_width
        self.min_height = min_height

    @property
    def name(self) -> str:
        return f"resolution(min={self.min_width}x{self.min_height})"

    def check(self, candidate: ImageCandidate) -> FilterResult:
        """Check if image meets minimum resolution requirements.

        Note: Checks both orientations - an image can be rotated to fit.
        """
        width, height = candidate.image.size

        # Check if image fits in either orientation
        fits_normal = width >= self.min_width and height >= self.min_height
        fits_rotated = height >= self.min_width and width >= self.min_height

        if fits_normal or fits_rotated:
            return FilterResult.accept()

        return FilterResult.reject(
            f"Resolution {width}x{height} below minimum {self.min_width}x{self.min_height}"
        )
