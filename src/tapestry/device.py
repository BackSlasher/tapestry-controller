#!/usr/bin/env python3
import argparse
from typing import NamedTuple

import PIL
import PIL.Image
import PIL.ImageOps
import requests

from .geometry import Dimensions


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("hostname")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("clear")
    draw_parser = subparsers.add_parser("draw")
    draw_parser.add_argument("-c", "--clear", action="store_true")
    draw_parser.add_argument("file")
    subparsers.add_parser("info")

    return parser.parse_args()


def clear(hostname):
    requests.post(f"http://{hostname}/clear").raise_for_status()


class EpdInfo(NamedTuple):
    width: int
    height: int
    temperature: int
    screen_model: str

    @classmethod
    def from_response(cls, resp):
        try:
            data = resp.json()
            return cls(
                width=int(data["width"]),
                height=int(data["height"]),
                temperature=int(data["temperature"]),
                screen_model=data["screen_model"],
            )
        except (KeyError, ValueError) as e:
            raise ValueError(
                f"Device response missing required field or invalid JSON: {e}. Response: {resp.text}"
            )


def info(hostname):
    resp = requests.get(f"http://{hostname}")
    resp.raise_for_status()
    return EpdInfo.from_response(resp)


def image_refit(image: PIL.Image, bounder: Dimensions) -> PIL.Image:
    bounder_ratio = bounder.width / bounder.height
    image_width, image_height = image.size

    image_width_by_height = int(image_height * bounder_ratio)
    image_height_by_width = int(image_width / bounder_ratio)
    if image_width > image_width_by_height:
        new_dimensions = Dimensions(image_width_by_height, image_height)
    else:
        new_dimensions = Dimensions(image_width, image_height_by_width)
    return PIL.ImageOps.fit(image, new_dimensions)


def convert_8bit_to_4bit(bytestring):
    fourbit = []
    for i in range(0, len(bytestring), 2):
        first_nibble = int(bytestring[i] / 17)
        second_nibble = int(bytestring[i + 1] / 17)
        fourbit += [first_nibble << 4 | second_nibble]
    fourbit = bytes(fourbit)
    return fourbit


def draw_unrotated(hostname, img: PIL.Image, clear: bool):
    """Draw image to device without any rotation - for QR positioning."""
    try:
        inf = info(hostname)
        img = image_refit(img, Dimensions(width=inf.width, height=inf.height))
        img = img.resize((inf.width, inf.height))
        img = img.convert("L")

        # NO rotation applied - image goes to screen as-is
        img_bytes = convert_8bit_to_4bit(img.tobytes())
        requests.post(
            f"http://{hostname}/draw",
            headers={
                "width": str(inf.width),
                "height": str(inf.height),
                "x": "0",
                "y": "0",
                "clear": "1" if clear else "0",
            },
            data=img_bytes,
        )
    except Exception as e:
        print(f"Error drawing to {hostname}: {e}")
        raise


def draw(hostname, img: PIL.Image, clear: bool, rotation: int = 0):
    try:
        inf = info(hostname)
        img = image_refit(img, Dimensions(width=inf.width, height=inf.height))
        img = img.resize((inf.width, inf.height))
        img = img.convert("L")

        # Apply device-specific rotation (in addition to any base rotation)
        if rotation != 0:
            img = img.rotate(
                -rotation, expand=False, fillcolor=255
            )  # negative for clockwise rotation

        img_bytes = convert_8bit_to_4bit(img.tobytes())
        requests.post(
            f"http://{hostname}/draw",
            headers={
                "width": str(inf.width),
                "height": str(inf.height),
                "x": "0",
                "y": "0",
                "clear": "1" if clear else "0",
            },
            data=img_bytes,
        )
    except Exception as e:
        print(f"Error drawing to {hostname}: {e}")
        raise


def main():
    args = parse_args()
    if args.command == "clear":
        clear(args.hostname)
    elif args.command == "info":
        print(info(args.hostname))
    elif args.command == "draw":
        img = PIL.Image.open(args.file)
        draw(args.hostname, img, args.clear)
    else:
        raise Exception(f"Unknown command {args.command}")


if __name__ == "__main__":
    main()
