"""Settings management for Tapestry controller using Pydantic Settings."""

import logging
from typing import Literal

import toml
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)

logger = logging.getLogger(__name__)


class GallerySettings(BaseModel):
    """Gallery screensaver settings."""

    wallpapers_dir: str = Field(
        default="wallpapers", description="Directory containing wallpaper images"
    )

    @field_validator("wallpapers_dir")
    @classmethod
    def validate_wallpapers_dir(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("wallpapers_dir cannot be empty")
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

    api_key: str = Field(
        default="", description="Pixabay API key"
    )
    keywords: str = Field(
        default="wallpaper", description="Keywords for image search"
    )
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

    @model_validator(mode='after')
    def validate_screensaver_config(self):
        if self.type == "pixabay" and not self.pixabay.api_key.strip():
            raise ValueError("Pixabay API key is required when using Pixabay screensaver")
        return self


class TapestrySettings(BaseSettings):
    """Main Tapestry settings."""

    screensaver: ScreensaverSettings = Field(
        default_factory=ScreensaverSettings, description="Screensaver configuration"
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
        file_path = self.model_config["toml_file"]
        """Save settings to TOML file."""
        with open(file_path, "w") as f:
            toml.dump(self.model_dump(), f)
        logger.info(f"Settings saved to {file_path}")


# Global settings instance
_settings: TapestrySettings = None


def get_settings() -> TapestrySettings:
    """Get the global settings instance."""
    global _settings
    if _settings is None:
        _settings = TapestrySettings()
    return _settings
