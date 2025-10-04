#!/usr/bin/env python3
"""CLI tool for QR code debug analysis."""

import argparse
import json
import sys
from pathlib import Path

import PIL.Image

from .qr_debug import analyze_qr_image


def parse_args():
    parser = argparse.ArgumentParser(
        description="Analyze QR codes in an image and generate debug visualization"
    )
    parser.add_argument("input_image", help="Path to input image file")
    parser.add_argument(
        "--output-image",
        help="Path for debug visualization output (default: input_debug.png)"
    )
    parser.add_argument(
        "--output-json",
        help="Path for JSON data output (default: print to stdout)"
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress non-JSON output"
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # Validate input file
    input_path = Path(args.input_image)
    if not input_path.exists():
        print(f"Error: Input file '{input_path}' does not exist", file=sys.stderr)
        sys.exit(1)

    # Set default output paths
    if args.output_image:
        output_image_path = Path(args.output_image)
    else:
        output_image_path = input_path.with_stem(f"{input_path.stem}_debug")

    try:
        # Load image
        if not args.quiet:
            print(f"Loading image: {input_path}")
        image = PIL.Image.open(input_path)

        # Analyze QR codes
        if not args.quiet:
            print("Analyzing QR codes...")
        debug_image, qr_info = analyze_qr_image(image)

        # Save debug image
        debug_image.save(output_image_path)
        if not args.quiet:
            print(f"Debug image saved: {output_image_path}")

        # Prepare JSON output
        output_data = {
            "input_image": str(input_path),
            "output_image": str(output_image_path),
            "total_found": len(qr_info),
            "qr_codes": qr_info
        }

        # Output JSON data
        if args.output_json:
            json_path = Path(args.output_json)
            with open(json_path, 'w') as f:
                json.dump(output_data, f, indent=2)
            if not args.quiet:
                print(f"JSON data saved: {json_path}")
        else:
            # Print to stdout
            print(json.dumps(output_data, indent=2))

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()