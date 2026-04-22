"""SQLite database for image tracking and feedback."""

import sqlite3
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ImageRecord:
    """Record of a staged image."""
    id: str  # UUID filename
    source_type: str  # reddit, collection
    source_name: str  # r/ThingsCutInHalfPorn, favorites
    original_url: Optional[str]
    title: Optional[str]
    staged_at: datetime
    status: str  # active, liked, rejected


@dataclass
class FeedbackRecord:
    """Record of user feedback on an image."""
    image_id: str
    action: str  # like, dislike, skip
    timestamp: datetime


class CurationDatabase:
    """SQLite database for curation tracking."""

    def __init__(self, db_path: str = ".tapestry-data/curation.db"):
        """Initialize database.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        """Initialize database schema."""
        with self._get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS images (
                    id TEXT PRIMARY KEY,
                    source_type TEXT NOT NULL,
                    source_name TEXT NOT NULL,
                    original_url TEXT,
                    title TEXT,
                    staged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT 'active'
                );

                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    image_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (image_id) REFERENCES images(id)
                );

                CREATE INDEX IF NOT EXISTS idx_images_status ON images(status);
                CREATE INDEX IF NOT EXISTS idx_images_source ON images(source_type, source_name);
                CREATE INDEX IF NOT EXISTS idx_feedback_image ON feedback(image_id);
            """)
            conn.commit()
        logger.info(f"Database initialized at {self.db_path}")

    def add_image(
        self,
        image_id: str,
        source_type: str,
        source_name: str,
        original_url: Optional[str] = None,
        title: Optional[str] = None,
    ) -> None:
        """Add an image record."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO images (id, source_type, source_name, original_url, title, staged_at, status)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, 'active')
                """,
                (image_id, source_type, source_name, original_url, title),
            )
            conn.commit()

    def get_image(self, image_id: str) -> Optional[ImageRecord]:
        """Get an image record by ID."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM images WHERE id = ?", (image_id,)
            ).fetchone()
            if row:
                return ImageRecord(
                    id=row["id"],
                    source_type=row["source_type"],
                    source_name=row["source_name"],
                    original_url=row["original_url"],
                    title=row["title"],
                    staged_at=datetime.fromisoformat(row["staged_at"]) if row["staged_at"] else None,
                    status=row["status"],
                )
        return None

    def set_status(self, image_id: str, status: str) -> None:
        """Update image status (active, liked, rejected)."""
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE images SET status = ? WHERE id = ?",
                (status, image_id),
            )
            conn.commit()

    def add_feedback(self, image_id: str, action: str) -> None:
        """Record user feedback on an image."""
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO feedback (image_id, action) VALUES (?, ?)",
                (image_id, action),
            )
            conn.commit()

    def like_image(self, image_id: str) -> None:
        """Mark image as liked."""
        self.set_status(image_id, "liked")
        self.add_feedback(image_id, "like")

    def reject_image(self, image_id: str) -> None:
        """Mark image as rejected."""
        self.set_status(image_id, "rejected")
        self.add_feedback(image_id, "dislike")

    def get_rejected_ids(self) -> List[str]:
        """Get list of rejected image IDs."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT id FROM images WHERE status = 'rejected'"
            ).fetchall()
            return [row["id"] for row in rows]

    def get_liked_ids(self) -> List[str]:
        """Get list of liked image IDs."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT id FROM images WHERE status = 'liked'"
            ).fetchall()
            return [row["id"] for row in rows]

    def get_active_images(self) -> List[ImageRecord]:
        """Get all active (non-rejected) images."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM images WHERE status = 'active' ORDER BY staged_at"
            ).fetchall()
            return [
                ImageRecord(
                    id=row["id"],
                    source_type=row["source_type"],
                    source_name=row["source_name"],
                    original_url=row["original_url"],
                    title=row["title"],
                    staged_at=datetime.fromisoformat(row["staged_at"]) if row["staged_at"] else None,
                    status=row["status"],
                )
                for row in rows
            ]

    def clear_staging(self) -> None:
        """Clear all images (for re-curation)."""
        with self._get_connection() as conn:
            # Keep rejected status but remove active images
            conn.execute("DELETE FROM images WHERE status = 'active'")
            conn.commit()

    def is_rejected(self, original_url: str) -> bool:
        """Check if an image URL was previously rejected."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM images WHERE original_url = ? AND status = 'rejected'",
                (original_url,),
            ).fetchone()
            return row is not None

    def get_stats(self) -> dict:
        """Get database statistics."""
        with self._get_connection() as conn:
            stats = {}
            for status in ["active", "liked", "rejected"]:
                count = conn.execute(
                    "SELECT COUNT(*) FROM images WHERE status = ?", (status,)
                ).fetchone()[0]
                stats[status] = count

            stats["total_feedback"] = conn.execute(
                "SELECT COUNT(*) FROM feedback"
            ).fetchone()[0]

            return stats
