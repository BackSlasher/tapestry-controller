#!/usr/bin/env python3
"""CLI tool for generating positioning QR codes."""

import argparse
import sys
from pathlib import Path

from .qr_generation import generate_positioning_qr_image


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate positioning QR code for a specific device"
    )
    parser.add_argument("width", type=int, help="Screen width in pixels")
    parser.add_argument("height", type=int, help="Screen height in pixels")
    parser.add_argument(
        "--ip", default="10.42.0.1",
        help="IP address of the device (default: 10.42.0.1)"
    )
    parser.add_argument(
        "--screen-type", dest="screen_type", default="ED097TC2",
        help="Screen type name (default: ED097TC2)"
    )
    parser.add_argument(
        "--output", "-o",
        help="Output file path (default: qr-{ip}.png)"
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # Set output path
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = Path(f"qr-{args.ip}.png")

    # Generate QR code
    print(f"Generating QR code for {args.ip} ({args.screen_type}) at {args.width}x{args.height}...")
    qr_image = generate_positioning_qr_image(args.ip, args.screen_type, args.width, args.height)

    # Save image
    qr_image.save(output_path)
    print(f"QR code saved to: {output_path}")



if __name__ == "__main__":
    main()
