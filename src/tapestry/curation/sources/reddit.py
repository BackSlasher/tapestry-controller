"""Reddit-based image source."""

import logging
import random
from io import BytesIO
from typing import Iterator, List, Literal, Optional
from urllib.parse import urlparse

import PIL.Image
import requests

from .base import ImageCandidate, Source

logger = logging.getLogger(__name__)


class RedditSource(Source):
    """Source that fetches images from Reddit subreddits."""

    is_local = False

    def __init__(
        self,
        subreddits: List[str],
        sort: Literal["top", "hot", "new", "rising"] = "top",
        time_period: Literal["hour", "day", "week", "month", "year", "all"] = "week",
        limit: int = 30,
        keywords_include: Optional[List[str]] = None,
        keywords_exclude: Optional[List[str]] = None,
        shuffle: bool = True,
    ):
        """Initialize Reddit source.

        Args:
            subreddits: List of subreddit names (without r/)
            sort: Sort order for posts
            time_period: Time period for "top" sort
            limit: Number of posts to fetch per subreddit
            keywords_include: If set, title must contain at least one of these
            keywords_exclude: If set, title must not contain any of these
            shuffle: Whether to shuffle results
        """
        self.subreddits = subreddits
        self.sort = sort
        self.time_period = time_period
        self.limit = limit
        self.keywords_include = [k.lower() for k in (keywords_include or [])]
        self.keywords_exclude = [k.lower() for k in (keywords_exclude or [])]
        self.shuffle = shuffle
        self._skip_filters = False  # Remote sources apply filters by default

    @property
    def name(self) -> str:
        return f"reddit:{'+'.join(self.subreddits)}"

    def should_skip_filters(self) -> bool:
        return self._skip_filters

    def set_skip_filters(self, skip: bool) -> None:
        self._skip_filters = skip

    def _fetch_subreddit_posts(self, subreddit: str) -> List[dict]:
        """Fetch posts from a single subreddit.

        Returns list of post data dicts with 'url' and 'title' keys.
        """
        url = f"https://www.reddit.com/r/{subreddit}/{self.sort}/.json"
        params = {"t": self.time_period, "limit": self.limit}
        headers = {"User-Agent": "Tapestry:v1.0 (by /u/tapestry_user)"}

        try:
            response = requests.get(url, params=params, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            logger.error(f"Failed to fetch from r/{subreddit}: {e}")
            return []

        posts = []
        for post in data.get("data", {}).get("children", []):
            post_data = post.get("data", {})
            post_url = post_data.get("url", "")
            title = post_data.get("title", "")

            # Skip deleted/removed posts
            if (
                not post_url
                or post_data.get("removed_by_category")
                or post_data.get("is_self")
            ):
                continue

            # Check if it's a direct image URL
            if not self._is_image_url(post_url):
                continue

            # Apply keyword filtering
            title_lower = title.lower()

            # Include filter: title must contain at least one keyword
            if self.keywords_include:
                if not any(kw in title_lower for kw in self.keywords_include):
                    continue

            # Exclude filter: title must not contain any keyword
            if self.keywords_exclude:
                if any(kw in title_lower for kw in self.keywords_exclude):
                    continue

            posts.append({
                "url": post_url,
                "title": title,
                "subreddit": subreddit,
            })

        return posts

    def _is_image_url(self, url: str) -> bool:
        """Check if URL points to an image."""
        parsed = urlparse(url)
        path_lower = parsed.path.lower()

        # Direct image extensions
        if path_lower.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
            return True

        # Known image hosts
        if any(domain in parsed.netloc.lower() for domain in ["i.imgur.com", "i.redd.it"]):
            return True

        return False

    def _download_image(self, url: str) -> Optional[PIL.Image.Image]:
        """Download and return image from URL."""
        headers = {"User-Agent": "Tapestry:v1.0 (by /u/tapestry_user)"}

        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            img = PIL.Image.open(BytesIO(response.content))
            img.load()  # Force load into memory
            return img
        except Exception as e:
            logger.warning(f"Failed to download image from {url}: {e}")
            return None

    def fetch(self) -> Iterator[ImageCandidate]:
        """Yield image candidates from Reddit."""
        all_posts = []

        for subreddit in self.subreddits:
            logger.info(f"Fetching from r/{subreddit}...")
            posts = self._fetch_subreddit_posts(subreddit)
            all_posts.extend(posts)
            logger.info(f"Found {len(posts)} image posts in r/{subreddit}")

        if not all_posts:
            logger.warning(f"No image posts found in {self.subreddits}")
            return

        if self.shuffle:
            random.shuffle(all_posts)

        for post in all_posts:
            img = self._download_image(post["url"])
            if img is None:
                continue

            yield ImageCandidate(
                image=img,
                metadata={
                    "source_type": "reddit",
                    "source_name": f"r/{post['subreddit']}",
                    "url": post["url"],
                    "title": post["title"],
                    "filename": f"{post['title'][:50]}.png",  # Will be renamed on save
                },
            )
