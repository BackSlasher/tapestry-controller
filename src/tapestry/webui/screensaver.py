"""Screensaver management module for Tapestry."""

import glob
import logging
import os
import random
import threading
from typing import Callable, Optional
from urllib.parse import urlparse

import PIL.Image
import requests

logger = logging.getLogger(__name__)


class ScreensaverManager:
    """Manages screensaver functionality with pluggable image sources."""

    def __init__(self, image_sender: Callable[[PIL.Image.Image], None]):
        """Initialize screensaver manager.

        Args:
            image_sender: Callable that takes a PIL Image and sends it to displays
        """
        self.image_sender = image_sender
        self._thread: Optional[threading.Thread] = None
        self._stop_event: Optional[threading.Event] = None
        self._active = False
        self._current_config: Optional[dict] = None

    @property
    def is_active(self) -> bool:
        """Check if screensaver is currently active."""
        return self._active

    def start(self, config: dict) -> None:
        """Start the screensaver with given configuration.

        Args:
            config: Screensaver configuration dictionary

        Raises:
            RuntimeError: If screensaver is already active or config is invalid
        """
        if self._active:
            raise RuntimeError("Screensaver is already active")

        # Validate configuration
        self._validate_config(config)

        # Store current config for next_image functionality
        self._current_config = config.copy()

        # Start screensaver thread
        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self._worker, args=(config,), daemon=True
        )
        self._active = True
        self._thread.start()

        logger.info(
            f"Screensaver started: type={config['type']}, interval={config['interval']}"
        )

    def stop(self, timeout: float = 2.0) -> None:
        """Stop the screensaver.

        Args:
            timeout: Maximum time to wait for thread to stop
        """
        if not self._active:
            return

        if self._stop_event:
            self._stop_event.set()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

        self._active = False
        self._thread = None
        self._stop_event = None
        self._current_config = None

        logger.info("Screensaver stopped")

    def next_image(self) -> bool:
        """Display the next image immediately.

        Returns:
            bool: True if an image was successfully displayed, False otherwise
        """
        if not self._current_config:
            logger.warning(
                "Cannot display next image: no screensaver configuration available"
            )
            return False

        try:
            image = self._get_next_image(self._current_config)
            if image:
                self.image_sender(image)
                logger.info("Next image displayed successfully")
                return True
            else:
                logger.warning("No image retrieved for next image request")
                return False
        except Exception as e:
            logger.error(f"Error displaying next image: {e}")
            return False

    def _validate_config(self, config: dict) -> None:
        """Validate screensaver configuration."""
        if not config.get("type"):
            raise ValueError("Screensaver type is required")

        if config["type"] == "gallery":
            wallpapers_dir = config.get("gallery", {}).get("wallpapers_dir") or ""
            if not wallpapers_dir or not os.path.exists(os.path.expanduser(wallpapers_dir)):
                raise ValueError(f"Invalid wallpapers directory: {wallpapers_dir}")

            images = self._get_gallery_images(wallpapers_dir)
            if not images:
                raise ValueError(f"No images found in {wallpapers_dir}")

        elif config["type"] == "pixabay":
            api_key = config.get("pixabay", {}).get("api_key")
            if not api_key:
                raise ValueError("Pixabay API key is required")

    def _worker(self, config: dict) -> None:
        """Main screensaver worker thread."""
        while not self._stop_event.is_set():
            try:
                image = self._get_next_image(config)
                if image:
                    self.image_sender(image)
                else:
                    logger.warning(
                        f"No image retrieved for screensaver type: {config['type']}"
                    )

            except Exception as e:
                logger.error(f"Screensaver error: {e}")

            # Wait for next cycle or stop signal
            self._stop_event.wait(config.get("interval", 60))

    def _get_next_image(self, config: dict) -> Optional[PIL.Image.Image]:
        """Get the next image based on screensaver type."""
        screensaver_type = config["type"]

        if screensaver_type == "gallery":
            return self._get_gallery_image(config["gallery"])
        elif screensaver_type == "reddit":
            return self._get_reddit_image(config["reddit"])
        elif screensaver_type == "pixabay":
            return self._get_pixabay_image(config["pixabay"])
        else:
            logger.error(f"Unknown screensaver type: {screensaver_type}")
            return None

    def _get_gallery_image(self, gallery_config: dict) -> Optional[PIL.Image.Image]:
        """Get random image from gallery directory."""
        wallpapers_dir = gallery_config["wallpapers_dir"]
        images = self._get_gallery_images(wallpapers_dir)

        if not images:
            logger.warning(f"No images found in {wallpapers_dir}")
            return None

        image_path = random.choice(images)
        logger.info(f"Gallery screensaver: displaying {os.path.basename(image_path)}")

        try:
            return PIL.Image.open(image_path)
        except Exception as e:
            logger.error(f"Error loading gallery image {image_path}: {e}")
            return None

    def _get_gallery_images(self, wallpapers_dir: str) -> list[str]:
        """Get list of image files from directory."""
        wallpapers_dir = os.path.expanduser(wallpapers_dir)
        patterns = ["*.png", "*.jpg", "*.jpeg", "*.gif", "*.bmp", "*.tiff", "*.webp"]
        images = []
        for pattern in patterns:
            images.extend(glob.glob(os.path.join(wallpapers_dir, pattern)))
        return images

    def _get_reddit_image(self, reddit_config: dict) -> Optional[PIL.Image.Image]:
        """Get random image from Reddit."""
        try:
            subreddit = reddit_config["subreddit"]
            sort = reddit_config["sort"]
            time_period = reddit_config["time_period"]
            limit = reddit_config["limit"]
            keywords = reddit_config.get("keywords", "")

            url = f"https://www.reddit.com/r/{subreddit}/{sort}/.json"
            params = {"t": time_period, "limit": limit}
            headers = {"User-Agent": "Tapestry:v1.0 (by /u/tapestry_user)"}

            logger.info(
                f"Reddit API request: {url} with params: {params}, keywords: '{keywords}'"
            )

            response = requests.get(url, params=params, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()

            total_posts = len(data.get("data", {}).get("children", []))
            logger.info(f"Reddit API returned {total_posts} posts")

            # Filter posts for valid image URLs
            image_posts = []
            filtered_posts = 0
            image_url_posts = 0
            keyword_filtered_posts = 0

            for post in data["data"]["children"]:
                post_data = post["data"]
                post_url = post_data.get("url", "")

                # Skip deleted/removed posts or posts without URLs
                if (
                    not post_url
                    or post_data.get("removed_by_category")
                    or post_data.get("is_self")
                ):
                    filtered_posts += 1
                    continue

                # Check if it's a direct image URL
                parsed_url = urlparse(post_url)
                is_image = False

                if parsed_url.path.lower().endswith(
                    (".png", ".jpg", ".jpeg", ".gif", ".webp")
                ):
                    is_image = True
                elif any(
                    domain in parsed_url.netloc.lower()
                    for domain in ["i.imgur.com", "i.redd.it"]
                ):
                    is_image = True

                if is_image:
                    image_url_posts += 1

                    # Apply keyword filtering if keywords are provided
                    title = post_data.get("title", "").lower()
                    if keywords.strip():
                        keyword_list = [
                            kw.strip().lower() for kw in keywords.split() if kw.strip()
                        ]
                        if not any(keyword in title for keyword in keyword_list):
                            keyword_filtered_posts += 1
                            continue

                    image_posts.append(
                        {
                            "url": post_url,
                            "title": post_data.get("title", "Reddit Wallpaper"),
                        }
                    )

            logger.info(
                f"Reddit filtering results: {filtered_posts} filtered out (deleted/self), "
                f"{image_url_posts} had image URLs, {keyword_filtered_posts} filtered by keywords, "
                f"{len(image_posts)} final candidates"
            )

            if not image_posts:
                error_msg = (
                    f"No valid image posts found after filtering. Total posts: {total_posts}, "
                    f"Image posts: {image_url_posts}, Keyword filtered: {keyword_filtered_posts}"
                )
                raise Exception(error_msg)

            # Select and download random image
            selected = random.choice(image_posts)
            logger.info(
                f"Selected Reddit post: '{selected['title']}' from {selected['url']}"
            )

            img_response = requests.get(selected["url"], headers=headers, timeout=30)
            img_response.raise_for_status()

            from io import BytesIO

            image = PIL.Image.open(BytesIO(img_response.content))
            logger.info(
                f"Reddit screensaver: successfully loaded image '{selected['title']}'"
            )

            return image

        except Exception as e:
            logger.error(f"Error fetching Reddit wallpaper: {e}")
            return None

    def _get_pixabay_image(self, pixabay_config: dict) -> Optional[PIL.Image.Image]:
        """Get random image from Pixabay."""
        try:
            api_key = pixabay_config["api_key"]
            keywords = pixabay_config["keywords"]
            per_page = pixabay_config["per_page"]

            if not api_key:
                raise Exception("Pixabay API key is required")

            url = "https://pixabay.com/api/"
            params = {
                "key": api_key,
                "q": keywords,
                "image_type": "photo",
                "orientation": "all",
                "min_width": 1200,
                "min_height": 800,
                "per_page": min(per_page, 200),  # API limit is 200
                "safesearch": "true",
            }

            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if not data.get("hits"):
                raise Exception(f"No images found for keywords: {keywords}")

            # Select random image
            selected = random.choice(data["hits"])

            # Get the largest available image
            image_url = (
                selected.get("fullHDURL")
                or selected.get("webformatURL")
                or selected.get("largeImageURL")
            )

            if not image_url:
                raise Exception("No suitable image URL found")

            # Download the image
            img_response = requests.get(image_url, timeout=30)
            img_response.raise_for_status()

            from io import BytesIO

            image = PIL.Image.open(BytesIO(img_response.content))
            logger.info(
                f"Pixabay screensaver: displaying image by {selected.get('user', 'unknown')} "
                f"(tags: {selected.get('tags', 'none')})"
            )

            return image

        except Exception as e:
            logger.error(f"Error fetching Pixabay wallpaper: {e}")
            return None
