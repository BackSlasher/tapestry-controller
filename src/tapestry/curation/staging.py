"""Staging manager for curated images."""

import hashlib
import json
import logging
import os
import random
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import PIL.Image

from .database import CurationDatabase
from .sources.base import ImageCandidate

logger = logging.getLogger(__name__)


@dataclass
class StagingState:
    """Persistent state for staged images playback."""

    current_image_id: Optional[str] = None  # Last shown image filename
    playlist_hash: str = ""  # To detect if playlist changed

    def to_dict(self) -> dict:
        return {
            "current_image_id": self.current_image_id,
            "playlist_hash": self.playlist_hash,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "StagingState":
        # Handle migration from old index-based state
        return cls(
            current_image_id=data.get("current_image_id"),
            playlist_hash=data.get("playlist_hash", ""),
        )


class StagingManager:
    """Manages the staging directory for curated images.

    The staging directory contains:
    - Image files (UUID-named .png files)
    - playlist.json: ordered list of filenames
    - state.json: current playback position

    Image metadata is stored in SQLite database.
    """

    def __init__(self, staging_path: str = ".tapestry-data/staging"):
        """Initialize staging manager.

        Args:
            staging_path: Path to staging directory (supports ~ expansion)
        """
        # Resolve to absolute path immediately to avoid CWD issues
        self.staging_path = Path(os.path.expanduser(staging_path)).resolve()
        self._ensure_directory()

        # Initialize database (in parent .tapestry-data directory)
        db_path = self.staging_path.parent / "curation.db"
        self.db = CurationDatabase(str(db_path))

    def _ensure_directory(self) -> None:
        """Ensure staging directory exists."""
        self.staging_path.mkdir(parents=True, exist_ok=True)

    @property
    def playlist_file(self) -> Path:
        return self.staging_path / "playlist.json"

    @property
    def state_file(self) -> Path:
        return self.staging_path / "state.json"

    @property
    def rejected_file(self) -> Path:
        return self.staging_path / "rejected.json"

    @property
    def last_result_file(self) -> Path:
        return self.staging_path / "last_curation.json"

    def save_last_result(self, result_dict: dict) -> None:
        """Save the last curation result to JSON."""
        from datetime import datetime
        result_dict["timestamp"] = datetime.now().isoformat()
        with open(self.last_result_file, "w") as f:
            json.dump(result_dict, f, indent=2)

    def get_last_result(self) -> Optional[dict]:
        """Load the last curation result, or None if not available."""
        if not self.last_result_file.exists():
            return None
        try:
            with open(self.last_result_file) as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to read last result: {e}")
            return None

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

        # Clear active images from database (keeps rejected/liked history)
        self.db.clear_staging()

        logger.info(f"Cleared staging directory: {self.staging_path}")

    def add_image(self, candidate: ImageCandidate) -> str:
        """Add an image to staging.

        Args:
            candidate: Image candidate to add

        Returns:
            Filename of saved image (UUID-based)
        """
        filename = f"{uuid.uuid4().hex[:12]}.png"
        filepath = self.staging_path / filename

        # Convert to RGB if necessary and save
        img = candidate.image
        if img.mode != "RGB":
            img = img.convert("RGB")

        img.save(filepath, "PNG")

        # Store metadata in database
        metadata = candidate.metadata
        self.db.add_image(
            image_id=filename,
            source_type=metadata.get("source_type", "unknown"),
            source_name=metadata.get("source_name", "unknown"),
            original_url=metadata.get("url"),
            title=metadata.get("title"),
        )

        logger.debug(f"Staged image: {filename} from {metadata.get('title', 'unknown')}")

        return filename

    def write_playlist(self, filenames: List[str], shuffle: bool = True) -> None:
        """Write playlist file.

        Args:
            filenames: List of image filenames in staging
            shuffle: Whether to shuffle the playlist
        """
        if shuffle:
            random.shuffle(filenames)

        self._write_playlist_raw(filenames, reset_state=True)

        logger.info(f"Wrote playlist with {len(filenames)} images (shuffled={shuffle})")

    def _write_playlist_raw(self, filenames: List[str], reset_state: bool = False) -> None:
        """Write playlist file without shuffling.

        Args:
            filenames: List of image filenames
            reset_state: Whether to reset playback state
        """
        playlist_data = {
            "images": filenames,
            "count": len(filenames),
        }

        with open(self.playlist_file, "w") as f:
            json.dump(playlist_data, f, indent=2)

        if reset_state:
            playlist_hash = hashlib.md5(json.dumps(filenames).encode()).hexdigest()[:8]
            self._save_state(StagingState(current_image_id=None, playlist_hash=playlist_hash))

    def append_to_playlist(self, filename: str) -> None:
        """Append a single image to the playlist.

        Args:
            filename: Image filename to append
        """
        playlist = self.get_playlist()
        playlist.append(filename)
        self._write_playlist_raw(playlist, reset_state=False)

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

    def _get_next_index(self, playlist: List[str], current_id: Optional[str]) -> int:
        """Get the index of the next image to show.

        Args:
            playlist: Current playlist
            current_id: Last shown image ID, or None

        Returns:
            Index of next image to show
        """
        if not current_id:
            return 0

        try:
            current_idx = playlist.index(current_id)
            return (current_idx + 1) % len(playlist)
        except ValueError:
            # Current image was deleted, start from beginning
            return 0

    def get_next_image(self) -> Optional[PIL.Image.Image]:
        """Get the next image in the playlist.

        Advances based on current_image_id and wraps around at the end.

        Returns:
            PIL Image or None if staging is empty
        """
        playlist = self.get_playlist()
        if not playlist:
            return None

        state = self._load_state()

        # Find next image index
        next_idx = self._get_next_index(playlist, state.current_image_id)

        # Try to load the image, skip missing ones
        attempts = 0
        while attempts < len(playlist):
            filename = playlist[next_idx]
            filepath = self.staging_path / filename

            if filepath.exists():
                try:
                    img = PIL.Image.open(filepath)
                    img.load()

                    # Update state with this image as current
                    state.current_image_id = filename
                    self._save_state(state)

                    logger.debug(f"Serving staged image: {filename}")
                    return img
                except Exception as e:
                    logger.error(f"Failed to load staged image {filename}: {e}")
            else:
                logger.warning(f"Staged image missing: {filename}")

            # Try next image
            next_idx = (next_idx + 1) % len(playlist)
            attempts += 1

        logger.error("No valid images found in playlist")
        return None

    def peek_current_image(self) -> Optional[PIL.Image.Image]:
        """Get the current (last shown) image without advancing.

        Returns:
            PIL Image or None if staging is empty or no image shown yet
        """
        state = self._load_state()
        if not state.current_image_id:
            return None

        filepath = self.staging_path / state.current_image_id
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

        # Calculate position for display (1-based)
        position = 0
        if state.current_image_id and state.current_image_id in playlist:
            position = playlist.index(state.current_image_id) + 1

        # Check if current image is liked
        current_liked = False
        if state.current_image_id:
            img_info = self.db.get_image(state.current_image_id)
            current_liked = img_info and img_info.status == "liked"

        return {
            "path": str(self.staging_path),
            "count": len(playlist),
            "current_image_id": state.current_image_id,
            "current_liked": current_liked,
            "position": position,
            "is_empty": len(playlist) == 0,
        }

    def get_current_image_filename(self) -> Optional[str]:
        """Get the filename of the current image (last shown).

        Returns:
            Filename string or None if no image shown yet
        """
        state = self._load_state()
        return state.current_image_id

    def get_rejected_list(self) -> List[str]:
        """Get list of rejected image filenames."""
        return self.db.get_rejected_ids()

    def reject_image(self, filename: str) -> None:
        """Reject an image, removing it from playlist and staging.

        Args:
            filename: Image filename to reject
        """
        # Mark as rejected in database
        self.db.reject_image(filename)

        # Remove from playlist
        playlist = self.get_playlist()
        if filename in playlist:
            # Find a nearby image to set as current if we're removing current
            state = self._load_state()
            if state.current_image_id == filename:
                idx = playlist.index(filename)
                if len(playlist) > 1:
                    # Move to previous image (or wrap to last)
                    new_idx = (idx - 1) % len(playlist)
                    # Skip the one we're about to remove
                    if new_idx >= idx:
                        new_idx = (new_idx - 1) % (len(playlist) - 1) if len(playlist) > 1 else 0
                    remaining = [p for p in playlist if p != filename]
                    state.current_image_id = remaining[min(new_idx, len(remaining) - 1)] if remaining else None
                else:
                    state.current_image_id = None
                self._save_state(state)

            playlist.remove(filename)
            # Rewrite playlist without shuffling
            self._write_playlist_raw(playlist, reset_state=False)

        # Delete the actual file
        filepath = self.staging_path / filename
        if filepath.exists():
            filepath.unlink()
            logger.info(f"Rejected and removed: {filename}")

    def like_image(self, filename: str) -> None:
        """Mark an image as liked in the database."""
        self.db.like_image(filename)
        logger.info(f"Liked: {filename}")

    def is_rejected(self, filename: str) -> bool:
        """Check if a filename is in the rejected list."""
        return filename in self.db.get_rejected_ids()

    def is_url_rejected(self, url: str) -> bool:
        """Check if an image URL was previously rejected."""
        return self.db.is_rejected(url)

    def get_image_info(self, filename: str) -> Optional[dict]:
        """Get metadata for an image."""
        record = self.db.get_image(filename)
        if record:
            return {
                "id": record.id,
                "source_type": record.source_type,
                "source_name": record.source_name,
                "original_url": record.original_url,
                "title": record.title,
                "staged_at": record.staged_at.isoformat() if record.staged_at else None,
                "status": record.status,
            }
        return None

    def get_stats(self) -> dict:
        """Get database statistics."""
        return self.db.get_stats()
