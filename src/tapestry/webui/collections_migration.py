"""Migration utilities for collections feature."""

import logging
import os
import shutil
from pathlib import Path

from .collections_manager import create_collection, get_collections_root

logger = logging.getLogger(__name__)


def ensure_default_collection(
    collections_dir: str = "~/.tapestry/collections",
    legacy_wallpapers_dir: str = "wallpapers",
) -> bool:
    """Ensure the default 'wallpapers' collection exists.

    If a legacy wallpapers directory exists and the collections directory is empty,
    migrates the legacy directory to a collection.

    Args:
        collections_dir: Path to collections directory
        legacy_wallpapers_dir: Path to legacy wallpapers directory

    Returns:
        True if default collection was created/exists, False otherwise
    """
    root = get_collections_root(collections_dir)
    default_collection_path = root / "wallpapers"

    # Check if default collection already exists
    if default_collection_path.exists():
        logger.info("Default 'wallpapers' collection already exists")
        return True

    # Check if we should migrate legacy wallpapers
    legacy_path = Path(os.path.expanduser(legacy_wallpapers_dir))

    if legacy_path.exists() and legacy_path.is_dir():
        # Check if legacy directory has any images
        image_patterns = [
            "*.png",
            "*.jpg",
            "*.jpeg",
            "*.gif",
            "*.bmp",
            "*.tiff",
            "*.webp",
        ]
        has_images = False

        for pattern in image_patterns:
            if list(legacy_path.glob(pattern)):
                has_images = True
                break

        if has_images:
            # Migrate legacy wallpapers to collection
            try:
                logger.info(
                    f"Migrating legacy wallpapers from {legacy_path} to collections"
                )
                shutil.copytree(legacy_path, default_collection_path)
                logger.info(
                    "Successfully migrated legacy wallpapers to 'wallpapers' collection"
                )
                return True
            except Exception as e:
                logger.error(f"Failed to migrate legacy wallpapers: {e}")
                # Fall through to create empty collection

    # Create empty default collection
    success, message = create_collection("wallpapers", collections_dir)
    if success:
        logger.info("Created default 'wallpapers' collection")
        return True
    else:
        logger.error(f"Failed to create default collection: {message}")
        return False


def migrate_legacy_wallpapers_if_needed() -> dict:
    """Check for and migrate legacy wallpapers if appropriate.

    Returns:
        Dict with migration status information
    """
    from ..settings import get_settings

    settings = get_settings()
    collections_dir = settings.screensaver.gallery.collections_dir
    legacy_dir = settings.screensaver.gallery.wallpapers_dir

    # Get collections root
    root = get_collections_root(collections_dir)

    # Check if collections directory is empty
    existing_collections = list(root.iterdir())

    # Check if legacy directory exists and has images
    legacy_path = Path(os.path.expanduser(legacy_dir))
    legacy_has_images = False

    if legacy_path.exists() and legacy_path.is_dir():
        image_patterns = [
            "*.png",
            "*.jpg",
            "*.jpeg",
            "*.gif",
            "*.bmp",
            "*.tiff",
            "*.webp",
        ]
        for pattern in image_patterns:
            if list(legacy_path.glob(pattern)):
                legacy_has_images = True
                break

    result = {
        "collections_exist": len(existing_collections) > 0,
        "legacy_exists": legacy_path.exists(),
        "legacy_has_images": legacy_has_images,
        "migration_needed": len(existing_collections) == 0 and legacy_has_images,
        "migrated": False,
    }

    # Perform migration if needed
    if result["migration_needed"]:
        if ensure_default_collection(collections_dir, legacy_dir):
            result["migrated"] = True
            logger.info("Automatic migration completed successfully")
        else:
            logger.warning("Automatic migration was needed but failed")

    return result
