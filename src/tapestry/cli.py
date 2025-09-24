#!/usr/bin/env python3
import argparse
import PIL.Image
from .controller import TapestryController


def parse_args():
    parser = argparse.ArgumentParser(
        description="Send images to distributed e-ink displays"
    )
    parser.add_argument("filename", help="Image to send to displays")
    parser.add_argument(
        "--devices-file",
        default="devices.yaml",
        help="YAML file containing device configuration",
    )
    parser.add_argument(
        "--debug-output-dir", help="Directory to save debug images (refit and layout)"
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # Load image
    image = PIL.Image.open(args.filename)

    # Create controller from config
    controller = TapestryController.from_config_file(args.devices_file)

    # Send image to displays
    controller.send_image(image, debug_output_dir=args.debug_output_dir)

    print(
        f"Successfully sent {args.filename} to {len(controller.config.devices)} devices"
    )


if __name__ == "__main__":
    main()
