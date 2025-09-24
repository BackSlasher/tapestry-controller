"""Settings management for Tapestry controller using Pydantic Settings."""

from pathlib import Path
from typing import Literal
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class GallerySettings(BaseModel):
    """Gallery screensaver settings."""
    wallpapers_dir: str = Field(default="wallpapers", description="Directory containing wallpaper images")

    @field_validator('wallpapers_dir')
    @classmethod
    def validate_wallpapers_dir(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("wallpapers_dir cannot be empty")
        return v.strip()


class RedditSettings(BaseModel):
    """Reddit screensaver settings."""
    subreddit: str = Field(default="aiwallpapers", description="Subreddit name (without r/)")
    time_period: Literal["hour", "day", "week", "month", "year", "all"] = Field(default="all", description="Time period for top posts")
    sort: Literal["top", "hot", "new", "rising"] = Field(default="top", description="Sort order")
    limit: int = Field(default=30, ge=1, le=100, description="Number of top posts to consider")

    @field_validator('subreddit')
    @classmethod
    def validate_subreddit(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("subreddit cannot be empty")
        cleaned = v.strip()
        # Basic validation for subreddit name format
        if not cleaned.replace('_', '').replace('-', '').isalnum():
            raise ValueError("subreddit name can only contain letters, numbers, underscores, and hyphens")
        return cleaned


class ScreensaverSettings(BaseModel):
    """Screensaver configuration."""
    enabled: bool = Field(default=False, description="Whether screensaver is enabled")
    type: Literal["gallery", "reddit"] = Field(default="gallery", description="Screensaver type")
    interval: int = Field(default=60, ge=1, le=3600, description="Interval between images in seconds")
    gallery: GallerySettings = Field(default_factory=GallerySettings, description="Gallery screensaver settings")
    reddit: RedditSettings = Field(default_factory=RedditSettings, description="Reddit screensaver settings")


class TapestrySettings(BaseSettings):
    """Main Tapestry settings."""
    screensaver: ScreensaverSettings = Field(default_factory=ScreensaverSettings, description="Screensaver configuration")

    model_config = SettingsConfigDict(
        toml_file="settings.toml",
        env_prefix="TAPESTRY_",
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="ignore"
    )

    def save_to_file(self, file_path: str = "settings.toml") -> None:
        """Save settings to TOML file."""
        try:
            import toml
            with open(file_path, 'w') as f:
                toml.dump(self.model_dump(), f)
            print(f"Settings saved to {file_path}")
        except ImportError:
            print(f"Warning: toml library not available, cannot save settings to {file_path}")
        except Exception as e:
            print(f"Error saving settings to {file_path}: {e}")

    def update_screensaver(self, **kwargs) -> None:
        """Update screensaver settings and save to file."""
        # Update the screensaver settings
        for key, value in kwargs.items():
            if hasattr(self.screensaver, key):
                setattr(self.screensaver, key, value)
            elif key.startswith('gallery_'):
                gallery_key = key.replace('gallery_', '')
                if hasattr(self.screensaver.gallery, gallery_key):
                    setattr(self.screensaver.gallery, gallery_key, value)
            elif key.startswith('reddit_'):
                reddit_key = key.replace('reddit_', '')
                if hasattr(self.screensaver.reddit, reddit_key):
                    setattr(self.screensaver.reddit, reddit_key, value)

        # Validate the updated settings
        self.model_validate(self.model_dump())

        # Save to file
        self.save_to_file()


# Global settings instance
_settings: TapestrySettings = None


def init_settings(settings_file: str = "settings.toml") -> TapestrySettings:
    """Initialize the global settings instance."""
    global _settings

    # Check if settings file exists
    settings_path = Path(settings_file)
    if settings_path.exists():
        print(f"Loading settings from {settings_file}")
        try:
            _settings = TapestrySettings(_toml_file=settings_file)
        except Exception as e:
            print(f"Error loading settings from {settings_file}: {e}")
            print("Using default settings")
            _settings = TapestrySettings()
    else:
        print(f"Settings file {settings_file} not found, using defaults")
        _settings = TapestrySettings()
        # Save default settings to file for next time
        _settings.save_to_file(settings_file)

    return _settings


def get_settings() -> TapestrySettings:
    """Get the global settings instance."""
    global _settings
    if _settings is None:
        _settings = init_settings()
    return _settings
