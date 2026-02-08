"""Collections manager for organizing and managing image collections."""

import glob
import logging
import os
import re
import shutil
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def validate_collection_name(name: str) -> tuple[bool, str]:
    """Validate collection name.

    Args:
        name: Collection name to validate

    Returns:
        Tuple of (is_valid, error_message). If is_valid is True, error_message will be empty string.
    """
    if not name or not name.strip():
        return False, "Collection name cannot be empty"

    name = name.strip()

    # Check for invalid characters
    if not re.match(r"^[a-zA-Z0-9\s_-]+$", name):
        return (
            False,
            "Collection name can only contain letters, numbers, spaces, hyphens, and underscores",
        )

    # Check length
    if len(name) > 100:
        return False, "Collection name too long (max 100 characters)"

    # Check for dangerous names
    dangerous_names = [".", "..", ".git", ".gitignore"]
    if name.lower() in [n.lower() for n in dangerous_names]:
        return False, f"Invalid collection name: {name}"

    return True, ""


def get_collections_root(collections_dir: str = "~/.tapestry/collections") -> Path:
    """Get the collections root directory, creating it if needed.

    Args:
        collections_dir: Path to collections directory

    Returns:
        Path object for collections directory
    """
    path = Path(os.path.expanduser(collections_dir))
    path.mkdir(parents=True, exist_ok=True)
    return path


def list_collections(collections_dir: str = "~/.tapestry/collections") -> list[dict]:
    """List all available collections.

    Args:
        collections_dir: Path to collections directory

    Returns:
        List of collection info dicts with keys: name, path, image_count
    """
    root = get_collections_root(collections_dir)
    collections = []

    for item in root.iterdir():
        if item.is_dir():
            # Count images in the collection
            image_count = len(get_collection_images(item))
            collections.append(
                {
                    "name": item.name,
                    "path": str(item),
                    "image_count": image_count,
                }
            )

    # Sort by name
    collections.sort(key=lambda c: c["name"].lower())
    return collections


def create_collection(
    name: str, collections_dir: str = "~/.tapestry/collections"
) -> tuple[bool, str]:
    """Create a new collection.

    Args:
        name: Collection name
        collections_dir: Path to collections directory

    Returns:
        Tuple of (success, message)
    """
    # Validate name
    is_valid, error_msg = validate_collection_name(name)
    if not is_valid:
        return False, error_msg

    # Get collection path
    root = get_collections_root(collections_dir)
    collection_path = root / name.strip()

    # Check if already exists
    if collection_path.exists():
        return False, f"Collection '{name}' already exists"

    # Create directory
    try:
        collection_path.mkdir(parents=True, exist_ok=False)
        logger.info(f"Created collection: {name}")
        return True, f"Collection '{name}' created successfully"
    except Exception as e:
        logger.error(f"Error creating collection '{name}': {e}")
        return False, f"Failed to create collection: {str(e)}"


def delete_collection(
    name: str, collections_dir: str = "~/.tapestry/collections"
) -> tuple[bool, str]:
    """Delete a collection and all its images.

    Args:
        name: Collection name
        collections_dir: Path to collections directory

    Returns:
        Tuple of (success, message)
    """
    # Validate name
    is_valid, error_msg = validate_collection_name(name)
    if not is_valid:
        return False, error_msg

    # Get collection path
    root = get_collections_root(collections_dir)
    collection_path = root / name.strip()

    # Check if exists
    if not collection_path.exists():
        return False, f"Collection '{name}' does not exist"

    # Delete directory
    try:
        shutil.rmtree(collection_path)
        logger.info(f"Deleted collection: {name}")
        return True, f"Collection '{name}' deleted successfully"
    except Exception as e:
        logger.error(f"Error deleting collection '{name}': {e}")
        return False, f"Failed to delete collection: {str(e)}"


def rename_collection(
    old_name: str, new_name: str, collections_dir: str = "~/.tapestry/collections"
) -> tuple[bool, str]:
    """Rename a collection.

    Args:
        old_name: Current collection name
        new_name: New collection name
        collections_dir: Path to collections directory

    Returns:
        Tuple of (success, message)
    """
    # Validate both names
    is_valid, error = validate_collection_name(old_name)
    if not is_valid:
        return False, f"Invalid old name: {error}"

    is_valid, error = validate_collection_name(new_name)
    if not is_valid:
        return False, f"Invalid new name: {error}"

    # Get paths
    root = get_collections_root(collections_dir)
    old_path = root / old_name.strip()
    new_path = root / new_name.strip()

    # Check if old exists
    if not old_path.exists():
        return False, f"Collection '{old_name}' does not exist"

    # Check if new already exists
    if new_path.exists():
        return False, f"Collection '{new_name}' already exists"

    # Rename directory
    try:
        old_path.rename(new_path)
        logger.info(f"Renamed collection: {old_name} -> {new_name}")
        return True, f"Collection renamed successfully"
    except Exception as e:
        logger.error(f"Error renaming collection '{old_name}' to '{new_name}': {e}")
        return False, f"Failed to rename collection: {str(e)}"


def get_collection_path(
    collection_name: str, collections_dir: str = "~/.tapestry/collections"
) -> Optional[Path]:
    """Get the path to a collection.

    Args:
        collection_name: Name of the collection
        collections_dir: Path to collections directory

    Returns:
        Path object if collection exists, None otherwise
    """
    root = get_collections_root(collections_dir)
    collection_path = root / collection_name.strip()

    if collection_path.exists() and collection_path.is_dir():
        return collection_path
    return None


def get_collection_images(collection_path: Path) -> list[str]:
    """Get list of image files in a collection.

    Args:
        collection_path: Path to the collection directory

    Returns:
        List of image file paths
    """
    patterns = ["*.png", "*.jpg", "*.jpeg", "*.gif", "*.bmp", "*.tiff", "*.webp"]
    images = []

    for pattern in patterns:
        images.extend(glob.glob(str(collection_path / pattern)))

    return sorted(images)


def list_collection_images(
    collection_name: str, collections_dir: str = "~/.tapestry/collections"
) -> Optional[list[dict]]:
    """List all images in a collection.

    Args:
        collection_name: Name of the collection
        collections_dir: Path to collections directory

    Returns:
        List of image info dicts with keys: filename, path, size_bytes, or None if collection doesn't exist
    """
    collection_path = get_collection_path(collection_name, collections_dir)
    if not collection_path:
        return None

    images = get_collection_images(collection_path)

    result = []
    for img_path in images:
        path_obj = Path(img_path)
        result.append(
            {
                "filename": path_obj.name,
                "path": str(path_obj),
                "size_bytes": path_obj.stat().st_size,
            }
        )

    return result


def delete_collection_image(
    collection_name: str,
    filename: str,
    collections_dir: str = "~/.tapestry/collections",
) -> tuple[bool, str]:
    """Delete an image from a collection.

    Args:
        collection_name: Name of the collection
        filename: Name of the image file to delete
        collections_dir: Path to collections directory

    Returns:
        Tuple of (success, message)
    """
    # Validate collection name
    is_valid, error = validate_collection_name(collection_name)
    if not is_valid:
        return False, error

    # Get collection path
    collection_path = get_collection_path(collection_name, collections_dir)
    if not collection_path:
        return False, f"Collection '{collection_name}' does not exist"

    # Validate filename (only basename, no path components)
    if "/" in filename or "\\" in filename or filename in [".", ".."]:
        return False, "Invalid filename"

    # Get image path
    image_path = collection_path / filename

    # Check if exists
    if not image_path.exists():
        return False, f"Image '{filename}' not found in collection '{collection_name}'"

    # Delete file
    try:
        image_path.unlink()
        logger.info(f"Deleted image: {filename} from collection: {collection_name}")
        return True, f"Image '{filename}' deleted successfully"
    except Exception as e:
        logger.error(
            f"Error deleting image '{filename}' from collection '{collection_name}': {e}"
        )
        return False, f"Failed to delete image: {str(e)}"


def save_uploaded_image(
    collection_name: str,
    file,
    filename: str,
    collections_dir: str = "~/.tapestry/collections",
) -> tuple[bool, str]:
    """Save an uploaded image to a collection.

    Args:
        collection_name: Name of the collection
        file: File object from Flask request.files
        filename: Name to save the file as
        collections_dir: Path to collections directory

    Returns:
        Tuple of (success, message)
    """
    # Validate collection name
    is_valid, error = validate_collection_name(collection_name)
    if not is_valid:
        return False, error

    # Get collection path
    collection_path = get_collection_path(collection_name, collections_dir)
    if not collection_path:
        return False, f"Collection '{collection_name}' does not exist"

    # Validate filename
    if "/" in filename or "\\" in filename or filename in [".", ".."]:
        return False, "Invalid filename"

    # Check file extension
    allowed_extensions = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".webp"}
    file_ext = Path(filename).suffix.lower()
    if file_ext not in allowed_extensions:
        return False, f"Invalid file type. Allowed: {', '.join(allowed_extensions)}"

    # Save file
    try:
        file_path = collection_path / filename
        file.save(str(file_path))
        logger.info(f"Saved image: {filename} to collection: {collection_name}")
        return True, f"Image '{filename}' uploaded successfully"
    except Exception as e:
        logger.error(
            f"Error saving image '{filename}' to collection '{collection_name}': {e}"
        )
        return False, f"Failed to save image: {str(e)}"
