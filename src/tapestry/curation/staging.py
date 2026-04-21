"""Staging manager for curated images."""

import hashlib
import json
import logging
import os
import random
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import PIL.Image

from .sources.base import ImageCandidate

logger = logging.getLogger(__name__)


@dataclass
class StagingState:
    """Persistent state for staged images playback."""

    current_index: int = 0
    playlist_hash: str = ""  # To detect if playlist changed

    def to_dict(self) -> dict:
        return {
            "current_index": self.current_index,
            "playlist_hash": self.playlist_hash,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "StagingState":
        return cls(
            current_index=data.get("current_index", 0),
            playlist_hash=data.get("playlist_hash", ""),
        )


class StagingManager:
    """Manages the staging directory for curated images.

    The staging directory contains:
    - Image files (numbered: 001.png, 002.png, etc.)
    - playlist.json: ordered list of filenames
    - state.json: current playback position
    """

    def __init__(self, staging_path: str = ".tapestry-data/staging"):
        """Initialize staging manager.

        Args:
            staging_path: Path to staging directory (supports ~ expansion)
        """
        # Resolve to absolute path immediately to avoid CWD issues
        self.staging_path = Path(os.path.expanduser(staging_path)).resolve()
        self._ensure_directory()

    def _ensure_directory(self) -> None:
        """Ensure staging directory exists."""
        self.staging_path.mkdir(parents=True, exist_ok=True)

    @property
    def playlist_file(self) -> Path:
        return self.staging_path / "playlist.json"

    @property
    def state_file(self) -> Path:
        return self.staging_path / "state.json"

    def clear(self) -> None:
        """Clear all staged images and reset state."""
        # Remove all image files
        for f in self.staging_path.glob("*.png"):
            f.unlink()
        for f in self.staging_path.glob("*.jpg"):
            f.unlink()

        # Remove playlist and state
        if self.playlist_file.exists():
            self.playlist_file.unlink()
        if self.state_file.exists():
            self.state_file.unlink()

        logger.info(f"Cleared staging directory: {self.staging_path}")

    def add_image(self, candidate: ImageCandidate, index: int) -> str:
        """Add an image to staging.

        Args:
            candidate: Image candidate to add
            index: Index number for filename

        Returns:
            Filename of saved image
        """
        filename = f"{index:03d}.png"
        filepath = self.staging_path / filename

        # Convert to RGB if necessary and save
        img = candidate.image
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        img.save(filepath, "PNG")
        logger.debug(f"Staged image: {filename} from {candidate.metadata.get('title', 'unknown')}")

        return filename

    def write_playlist(self, filenames: List[str], shuffle: bool = True) -> None:
        """Write playlist file.

        Args:
            filenames: List of image filenames in staging
            shuffle: Whether to shuffle the playlist
        """
        if shuffle:
            random.shuffle(filenames)

        playlist_data = {
            "images": filenames,
            "count": len(filenames),
        }

        with open(self.playlist_file, "w") as f:
            json.dump(playlist_data, f, indent=2)

        # Reset state since playlist changed
        playlist_hash = hashlib.md5(json.dumps(filenames).encode()).hexdigest()[:8]
        self._save_state(StagingState(current_index=0, playlist_hash=playlist_hash))

        logger.info(f"Wrote playlist with {len(filenames)} images (shuffled={shuffle})")

    def get_playlist(self) -> List[str]:
        """Get current playlist.

        Returns:
            List of image filenames in playlist order
        """
        if not self.playlist_file.exists():
            return []

        try:
            with open(self.playlist_file) as f:
                data = json.load(f)
            return data.get("images", [])
        except Exception as e:
            logger.warning(f"Failed to read playlist: {e}")
            return []

    def _load_state(self) -> StagingState:
        """Load playback state."""
        if not self.state_file.exists():
            return StagingState()

        try:
            with open(self.state_file) as f:
                data = json.load(f)
            return StagingState.from_dict(data)
        except Exception as e:
            logger.warning(f"Failed to read state: {e}")
            return StagingState()

    def _save_state(self, state: StagingState) -> None:
        """Save playback state."""
        with open(self.state_file, "w") as f:
            json.dump(state.to_dict(), f)

    def get_next_image(self) -> Optional[PIL.Image.Image]:
        """Get the next image in the playlist.

        Advances the current index and wraps around at the end.

        Returns:
            PIL Image or None if staging is empty
        """
        playlist = self.get_playlist()
        if not playlist:
            return None

        state = self._load_state()

        # Check if playlist changed (hash mismatch)
        current_hash = hashlib.md5(json.dumps(playlist).encode()).hexdigest()[:8]
        if state.playlist_hash != current_hash:
            logger.info("Playlist changed, resetting index")
            state = StagingState(current_index=0, playlist_hash=current_hash)

        # Wrap around if needed
        if state.current_index >= len(playlist):
            state.current_index = 0

        # Get current image
        filename = playlist[state.current_index]
        filepath = self.staging_path / filename

        if not filepath.exists():
            logger.warning(f"Staged image missing: {filename}")
            # Try to recover by advancing to next
            state.current_index = (state.current_index + 1) % len(playlist)
            self._save_state(state)
            return self.get_next_image()  # Recursive, but bounded by playlist length

        try:
            img = PIL.Image.open(filepath)
            img.load()
        except Exception as e:
            logger.error(f"Failed to load staged image {filename}: {e}")
            state.current_index = (state.current_index + 1) % len(playlist)
            self._save_state(state)
            return None

        # Advance index for next call
        state.current_index = (state.current_index + 1) % len(playlist)
        self._save_state(state)

        logger.debug(f"Serving staged image: {filename} (next index: {state.current_index})")
        return img

    def peek_current_image(self) -> Optional[PIL.Image.Image]:
        """Get the current image without advancing.

        Returns:
            PIL Image or None if staging is empty
        """
        playlist = self.get_playlist()
        if not playlist:
            return None

        state = self._load_state()

        # Wrap around if needed
        index = state.current_index % len(playlist) if playlist else 0
        filename = playlist[index]
        filepath = self.staging_path / filename

        if not filepath.exists():
            return None

        try:
            img = PIL.Image.open(filepath)
            img.load()
            return img
        except Exception:
            return None

    def is_empty(self) -> bool:
        """Check if staging has no images."""
        return len(self.get_playlist()) == 0

    def count(self) -> int:
        """Get number of staged images."""
        return len(self.get_playlist())

    def get_info(self) -> dict:
        """Get staging information for status display."""
        playlist = self.get_playlist()
        state = self._load_state()

        return {
            "path": str(self.staging_path),
            "count": len(playlist),
            "current_index": state.current_index,
            "is_empty": len(playlist) == 0,
        }
