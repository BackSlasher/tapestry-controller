from typing import NamedTuple

import PIL.Image
import PIL.ImageOps

from .geometry import Dimensions, Point, Rectangle


class ResizeResult(NamedTuple):
    image: PIL.Image.Image
    px_in_unit: int


def image_refit(image: PIL.Image.Image, bounder: Dimensions) -> ResizeResult:
    bounder_ratio = bounder.width / bounder.height
    image_width, image_height = image.size

    image_width_by_height = int(image_height * bounder_ratio)
    image_height_by_width = int(image_width / bounder_ratio)
    if image_width > image_width_by_height:
        new_dimensions = Dimensions(image_width_by_height, image_height)
    else:
        new_dimensions = Dimensions(image_width, image_height_by_width)
    px_in_unit = int(new_dimensions.width / bounder.width)
    return ResizeResult(PIL.ImageOps.fit(image, new_dimensions), px_in_unit)


def image_crop(image: PIL.Image.Image, rectangle: Rectangle) -> PIL.Image.Image:
    original_dimensions = Dimensions(image.size[0], image.size[1])
    new_image = PIL.Image.new(
        image.mode,
        size=(original_dimensions.width * 3, original_dimensions.height * 3),
    )
    # Add buffer coords to the rectangle
    new_rectangle = Rectangle(
        start=Point(
            x=rectangle.start.x + original_dimensions.width,
            y=rectangle.start.y + original_dimensions.height,
        ),
        dimensions=Dimensions(
            width=rectangle.dimensions.width,
            height=rectangle.dimensions.height,
        ),
    )
    rectangle = new_rectangle
    new_image.paste(
        image,
        box=(original_dimensions),
    )
    image = new_image
    image = image.crop(
        (
            rectangle.start.x,
            rectangle.start.y,
            rectangle.start.x + rectangle.dimensions.width,
            rectangle.start.y + rectangle.dimensions.height,
        )
    )
    return image
