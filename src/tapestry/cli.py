#!/usr/bin/env python3
"""Tapestry CLI - distributed e-ink display controller."""

import argparse
import logging
import os
import sys
from typing import Optional

import PIL.Image

from .controller import TapestryController
from .curation import CurationManager
from .settings import get_settings


def setup_logging(verbose: bool = False) -> None:
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="[%(levelname)s] %(message)s",
    )


# =============================================================================
# Send command
# =============================================================================


def cmd_send(args: argparse.Namespace) -> int:
    """Send an image to displays."""
    setup_logging(args.verbose)

    # Load image
    image = PIL.Image.open(args.filename)

    # Create controller from config
    controller = TapestryController.from_config_file(args.devices_file)

    # Send image to displays
    controller.send_image(image, debug_output_dir=args.debug_output_dir)

    print(f"Sent {args.filename} to {len(controller.config.devices)} devices")
    return 0


# =============================================================================
# Curate command
# =============================================================================


def cmd_curate(args: argparse.Namespace) -> int:
    """Run the curation pipeline."""
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)

    settings = get_settings()

    # Initialize curation manager
    manager = CurationManager()

    # Get collections dir from gallery settings for backwards compat
    collections_dir = settings.screensaver.gallery.collections_dir

    # Configure from settings
    config = settings.curation.to_manager_config(collections_dir=collections_dir)
    manager.configure_from_dict(config)

    # Check if we have any sources configured
    if not config["sources"]:
        print("No sources configured. Add sources to settings.toml under [curation.sources]")
        print("\nExample configuration:")
        print("""
[[curation.sources]]
type = "collection"
name = "favorites"

[[curation.sources]]
type = "reddit"
subreddits = ["ImaginaryFallout", "RetroFuturism"]
sort = "top"
time_period = "week"
limit = 30
""")
        return 1

    # Run curation
    print(f"Running curation (dry_run={args.dry_run})...")
    result = manager.curate(dry_run=args.dry_run)

    # Print results
    print(f"\nCuration complete:")
    print(f"  Staged: {result.staged_count}")
    print(f"  Filtered: {result.filtered_count}")
    print(f"  Total candidates: {result.total_candidates}")

    if result.sources_summary:
        print(f"\nBy source:")
        for source, stats in result.sources_summary.items():
            print(f"  {source}:")
            print(f"    Candidates: {stats['candidates']}")
            print(f"    Staged: {stats['staged']}")
            print(f"    Filtered: {stats['filtered']}")

    if not args.dry_run:
        info = manager.get_staging_info()
        print(f"\nStaging directory: {info['path']}")
        print(f"Images staged: {info['count']}")

    return 0


# =============================================================================
# Demo command
# =============================================================================


def cmd_demo(args: argparse.Namespace) -> int:
    """Run in demo mode - display images without real hardware."""
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)

    settings = get_settings()

    # Initialize curation manager
    curation = CurationManager()
    collections_dir = settings.screensaver.gallery.collections_dir
    config = settings.curation.to_manager_config(collections_dir=collections_dir)
    curation.configure_from_dict(config)

    # Demo output directory
    demo_dir = os.path.expanduser(args.output_dir)
    os.makedirs(demo_dir, exist_ok=True)

    print(f"Demo mode: images will be saved to {demo_dir}")

    # Image counter for filenames
    image_counter = [0]

    def demo_image_sender(image: PIL.Image.Image) -> None:
        """Save image to demo directory instead of sending to displays."""
        image_counter[0] += 1
        filename = f"demo_{image_counter[0]:03d}.png"
        filepath = os.path.join(demo_dir, filename)

        # Convert to RGB if needed
        if image.mode in ("RGBA", "P"):
            image = image.convert("RGB")

        # Also convert to grayscale to simulate e-ink
        gray = image.convert("L")

        # Save both versions
        image.save(filepath, "PNG")
        gray.save(filepath.replace(".png", "_eink.png"), "PNG")

        print(f"Saved: {filename} (and {filename.replace('.png', '_eink.png')})")

        # Also display info
        print(f"  Size: {image.size[0]}x{image.size[1]}")

    # Import the new screensaver
    from .webui.screensaver_v2 import ScreensaverV2

    screensaver = ScreensaverV2(curation, demo_image_sender)

    if args.once:
        # Just show one image and exit
        print("\nFetching one image...")
        if screensaver.next_image():
            print("Done!")
            return 0
        else:
            print("Failed to get image")
            return 1
    else:
        # Run continuous demo
        print(f"\nStarting demo screensaver (interval: {args.interval}s)")
        print("Press Ctrl+C to stop\n")

        screensaver.start(interval=args.interval)

        try:
            # Keep running until interrupted
            import time
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopping...")
            screensaver.stop()
            print("Demo stopped")

        return 0


# =============================================================================
# Staging command
# =============================================================================


def cmd_staging(args: argparse.Namespace) -> int:
    """Show staging status."""
    setup_logging(args.verbose)

    settings = get_settings()
    curation = CurationManager(staging_path=settings.curation.staging_path)

    info = curation.get_staging_info()

    print(f"Staging directory: {info['path']}")
    print(f"Images: {info['count']}")
    print(f"Current index: {info['current_index']}")
    print(f"Empty: {info['is_empty']}")

    if args.list:
        playlist = curation.staging.get_playlist()
        if playlist:
            print(f"\nPlaylist ({len(playlist)} images):")
            for i, filename in enumerate(playlist):
                marker = " <-- current" if i == info['current_index'] else ""
                print(f"  {i}: {filename}{marker}")
        else:
            print("\nPlaylist is empty")

    return 0


# =============================================================================
# Main parser
# =============================================================================


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Tapestry - distributed e-ink display controller",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose output"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Send command (default behavior for backwards compatibility)
    send_parser = subparsers.add_parser("send", help="Send an image to displays")
    send_parser.add_argument("filename", help="Image to send to displays")
    send_parser.add_argument(
        "--devices-file",
        default="devices.yaml",
        help="YAML file containing device configuration",
    )
    send_parser.add_argument(
        "--debug-output-dir", help="Directory to save debug images"
    )
    send_parser.set_defaults(func=cmd_send)

    # Curate command
    curate_parser = subparsers.add_parser(
        "curate", help="Run the curation pipeline"
    )
    curate_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without staging images",
    )
    curate_parser.set_defaults(func=cmd_curate)

    # Demo command
    demo_parser = subparsers.add_parser(
        "demo", help="Run in demo mode (no hardware required)"
    )
    demo_parser.add_argument(
        "--output-dir",
        default=".tapestry-data/demo",
        help="Directory to save demo images",
    )
    demo_parser.add_argument(
        "--interval",
        type=int,
        default=10,
        help="Seconds between images (default: 10)",
    )
    demo_parser.add_argument(
        "--once",
        action="store_true",
        help="Show one image and exit",
    )
    demo_parser.set_defaults(func=cmd_demo)

    # Staging command
    staging_parser = subparsers.add_parser(
        "staging", help="Show staging status"
    )
    staging_parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="List all images in playlist",
    )
    staging_parser.set_defaults(func=cmd_staging)

    args = parser.parse_args()

    # Handle no command (backwards compatibility: treat as send if filename provided)
    if args.command is None:
        # Check if there's a positional arg that looks like a filename
        if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
            # Legacy mode: tapestry <filename>
            args.filename = sys.argv[1]
            args.devices_file = "devices.yaml"
            args.debug_output_dir = None
            return cmd_send(args)
        else:
            parser.print_help()
            return 1

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
