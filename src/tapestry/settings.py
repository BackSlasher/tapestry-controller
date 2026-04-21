"""Settings management for Tapestry controller using Pydantic Settings."""

import logging
import secrets
from typing import List, Literal, Optional, Union

import toml
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Curation Settings
# =============================================================================


class CurationFilterSettings(BaseModel):
    """Filter settings for curation pipeline."""

    enabled: bool = Field(default=True, description="Master switch for filters")
    min_width: int = Field(default=1920, ge=0, description="Minimum image width")
    min_height: int = Field(default=1080, ge=0, description="Minimum image height")
    min_contrast: int = Field(
        default=150, ge=0, le=255, description="Minimum contrast (0-255)"
    )
    min_histogram_entropy: Optional[float] = Field(
        default=None, ge=0, le=8, description="Minimum histogram entropy (0-8)"
    )
    keywords_exclude: List[str] = Field(
        default_factory=list, description="Reject if title contains any of these"
    )
    keywords_include: List[str] = Field(
        default_factory=list,
        description="Require title to contain at least one of these",
    )


class CollectionSourceSettings(BaseModel):
    """Settings for a collection source."""

    type: Literal["collection"] = "collection"
    name: str = Field(description="Collection name")
    shuffle: bool = Field(default=True, description="Shuffle image order")
    skip_filters: Optional[bool] = Field(
        default=None, description="Skip filters (default: True for local sources)"
    )


class RedditSourceSettings(BaseModel):
    """Settings for a Reddit source."""

    type: Literal["reddit"] = "reddit"
    subreddits: List[str] = Field(description="List of subreddit names")
    sort: Literal["top", "hot", "new", "rising"] = Field(
        default="top", description="Sort order"
    )
    time_period: Literal["hour", "day", "week", "month", "year", "all"] = Field(
        default="week", description="Time period for top sort"
    )
    limit: int = Field(default=30, ge=1, le=100, description="Posts per subreddit")
    keywords_include: List[str] = Field(
        default_factory=list, description="Title must contain at least one"
    )
    keywords_exclude: List[str] = Field(
        default_factory=list, description="Title must not contain any"
    )
    shuffle: bool = Field(default=True, description="Shuffle results")
    skip_filters: Optional[bool] = Field(
        default=None, description="Skip filters (default: False for remote sources)"
    )


# Union type for source settings
SourceSettings = Union[CollectionSourceSettings, RedditSourceSettings]


class CurationSettings(BaseModel):
    """Curation pipeline settings."""

    staging_path: str = Field(
        default=".tapestry-data/staging", description="Path to staging directory"
    )
    count: int = Field(default=20, ge=1, le=100, description="Number of images to stage")
    shuffle: bool = Field(default=True, description="Shuffle final playlist")
    interval: int = Field(
        default=86400, ge=60, description="Seconds between auto-curations"
    )
    filters: CurationFilterSettings = Field(
        default_factory=CurationFilterSettings, description="Filter settings"
    )
    sources: List[SourceSettings] = Field(
        default_factory=list, description="List of image sources"
    )

    def to_manager_config(self, collections_dir: str = ".tapestry-data/collections") -> dict:
        """Convert to config dict for CurationManager.configure_from_dict()."""
        return {
            "staging_path": self.staging_path,
            "count": self.count,
            "shuffle": self.shuffle,
            "interval": self.interval,
            "collections_dir": collections_dir,
            "filters": {
                "enabled": self.filters.enabled,
                "min_width": self.filters.min_width,
                "min_height": self.filters.min_height,
                "min_contrast": self.filters.min_contrast,
                "min_histogram_entropy": self.filters.min_histogram_entropy,
                "keywords_exclude": self.filters.keywords_exclude,
                "keywords_include": self.filters.keywords_include,
            },
            "sources": [s.model_dump() for s in self.sources],
        }


# =============================================================================
# Legacy Screensaver Settings (for backwards compatibility during migration)
# =============================================================================


class GallerySettings(BaseModel):
    """Gallery screensaver settings."""

    wallpapers_dir: str = Field(
        default="wallpapers",
        description="Legacy: Directory containing wallpaper images (deprecated)",
    )
    collections_dir: str = Field(
        default=".tapestry-data/collections",
        description="Root directory for image collections",
    )
    selected_collection: str = Field(
        default="wallpapers", description="Name of the currently selected collection"
    )

    @field_validator("wallpapers_dir")
    @classmethod
    def validate_wallpapers_dir(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("wallpapers_dir cannot be empty")
        return v.strip()

    @field_validator("collections_dir")
    @classmethod
    def validate_collections_dir(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("collections_dir cannot be empty")
        return v.strip()

    @field_validator("selected_collection")
    @classmethod
    def validate_selected_collection(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("selected_collection cannot be empty")
        # Validate collection name format
        import re

        if not re.match(r"^[a-zA-Z0-9\s_-]+$", v.strip()):
            raise ValueError(
                "collection name can only contain letters, numbers, spaces, hyphens, and underscores"
            )
        return v.strip()


class RedditSettings(BaseModel):
    """Reddit screensaver settings."""

    subreddit: str = Field(
        default="aiwallpapers", description="Subreddit name (without r/)"
    )
    time_period: Literal["hour", "day", "week", "month", "year", "all"] = Field(
        default="all", description="Time period for top posts"
    )
    sort: Literal["top", "hot", "new", "rising"] = Field(
        default="top", description="Sort order"
    )
    limit: int = Field(
        default=30, ge=1, le=100, description="Number of top posts to consider"
    )

    @field_validator("subreddit")
    @classmethod
    def validate_subreddit(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("subreddit cannot be empty")
        cleaned = v.strip()
        # Basic validation for subreddit name format
        if not cleaned.replace("_", "").replace("-", "").isalnum():
            raise ValueError(
                "subreddit name can only contain letters, numbers, underscores, and hyphens"
            )
        return cleaned


class PixabaySettings(BaseModel):
    """Pixabay screensaver settings."""

    api_key: str = Field(default="", description="Pixabay API key")
    keywords: str = Field(default="wallpaper", description="Keywords for image search")
    per_page: int = Field(
        default=20, ge=3, le=200, description="Number of images per request"
    )

    @field_validator("keywords")
    @classmethod
    def validate_keywords(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("keywords cannot be empty")
        return v.strip()


class ScreensaverSettings(BaseModel):
    """Screensaver configuration."""

    enabled: bool = Field(default=False, description="Whether screensaver is enabled")
    type: Literal["gallery", "reddit", "pixabay"] = Field(
        default="gallery", description="Screensaver type"
    )
    interval: int = Field(
        default=60, ge=1, le=3600, description="Interval between images in seconds"
    )
    gallery: GallerySettings = Field(
        default_factory=GallerySettings, description="Gallery screensaver settings"
    )
    reddit: RedditSettings = Field(
        default_factory=RedditSettings, description="Reddit screensaver settings"
    )
    pixabay: PixabaySettings = Field(
        default_factory=PixabaySettings, description="Pixabay screensaver settings"
    )

    @model_validator(mode="after")
    def validate_screensaver_config(self):
        if self.type == "pixabay" and not self.pixabay.api_key.strip():
            raise ValueError(
                "Pixabay API key is required when using Pixabay screensaver"
            )
        return self


class WebUISettings(BaseModel):
    """Web UI settings."""

    secret_key: str = Field(
        default="", description="Flask secret key for session security"
    )

    def ensure_secret_key(self) -> str:
        """Ensure a secure secret key exists, generating one if needed."""
        if not self.secret_key or self.secret_key == "tapestry-webui-secret-key":
            # Generate a secure 32-byte (256-bit) secret key
            self.secret_key = secrets.token_hex(32)
            logger.info("Generated new secure Flask secret key")
        return self.secret_key


class NewScreensaverSettings(BaseModel):
    """New simplified screensaver settings (uses staging)."""

    enabled: bool = Field(default=False, description="Whether screensaver is enabled")
    interval: int = Field(
        default=300, ge=10, le=3600, description="Seconds between image changes"
    )


class TapestrySettings(BaseSettings):
    """Main Tapestry settings."""

    # New curation system
    curation: CurationSettings = Field(
        default_factory=CurationSettings, description="Curation pipeline configuration"
    )

    # Legacy screensaver settings (for backwards compatibility)
    screensaver: ScreensaverSettings = Field(
        default_factory=ScreensaverSettings, description="Legacy screensaver configuration"
    )

    # New screensaver settings
    screensaver_v2: NewScreensaverSettings = Field(
        default_factory=NewScreensaverSettings,
        description="New screensaver configuration (uses staging)",
    )

    webui: WebUISettings = Field(
        default_factory=WebUISettings, description="Web UI configuration"
    )

    model_config = SettingsConfigDict(
        toml_file="settings.toml",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            TomlConfigSettingsSource(settings_cls),
            init_settings,
            env_settings,
            dotenv_settings,
            file_secret_settings,
        )

    def save_to_file(self) -> None:
        """Save settings to TOML file."""
        file_path = self.model_config["toml_file"]
        with open(file_path, "w") as f:
            toml.dump(self.model_dump(), f)
        logger.info(f"Settings saved to {file_path}")

    def ensure_secure_webui_config(self) -> str:
        """Ensure secure web UI configuration, auto-saving if changes made."""
        old_secret = self.webui.secret_key
        secret_key = self.webui.ensure_secret_key()

        # If the secret key was generated/changed, save to file
        if secret_key != old_secret:
            self.save_to_file()
            logger.info("Auto-saved settings with new secure secret key")

        return secret_key


# Global settings instance
_settings: TapestrySettings | None = None


def get_settings() -> TapestrySettings:
    """Get the global settings instance."""
    global _settings
    if _settings is None:
        _settings = TapestrySettings()
    return _settings
