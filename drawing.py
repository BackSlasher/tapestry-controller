from typing import NamedTuple
import math
import PIL.Image

class Dimensions(NamedTuple):
    width: int
    height: int

class Point(NamedTuple):
    x: int
    y: int

    def __add__(self, other: Dimensions) -> 'Point':
        return Point(
            self.x + other.width,
            self.y + other.height,
        )

class Rectangle(NamedTuple):
    start: Point
    dimensions: Dimensions
    rotation_deg: int

    def get_corners(self) -> list[Point]:
        ret = []
        rotation_rad_width = math.radians(self.rotation_deg)
        # Y is upside down because top-left is 0,0
        delta_width = Dimensions(
            width=int(self.dimensions.width * math.cos(rotation_rad_width)),
            height=0 - int(self.dimensions.height * math.sin(rotation_rad_width)),
        )
        rotation_rad_height = math.radians(self.rotation_deg - 90)
        delta_height = Dimensions(
            width=int(self.dimensions.width * math.cos(rotation_rad_height)),
            height=0 - int(self.dimensions.height * math.sin(rotation_rad_height)),
        )
        return [
            # left top
            self.start,
            # right top
            self.start + delta_width,
            # left bottom
            self.start + delta_height,
            # right bottom
            self.start + delta_width + delta_height
        ]

    @staticmethod
    def bounding_rectangle(rectangles: list['Rectangle']) -> 'Rectangle':
        all_points_deep = [r.get_corners() for r in rectangles]
        all_points = [item for sublist in all_points_deep for item in sublist]
        all_x = {p.x for p in all_points}
        all_y = {p.y for p in all_points}

        return Rectangle(
            start=Point(
                x=min(all_x),
                y=min(all_y),
            ),
            dimensions=Dimensions(
                width=(max(all_x) - min(all_x)),
                height=(max(all_y) - min(all_y)),
            ),
            rotation_deg=0,
        )

# Image functions

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

def image_crop(image: PIL.Image, rectangle: Rectangle) -> PIL.Image:
    # image.save('/tmp/blu/1.png')
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
        rotation_deg=rectangle.rotation_deg,
    )
    rectangle=new_rectangle
    new_image.paste(
        image,
        box=(original_dimensions),
    )
    image = new_image
    # image.save('/tmp/blu/2.png')
    image = image.rotate(
        rectangle.rotation_deg,
        center=(rectangle.start),
    )
    # image.save('/tmp/blu/3.png')
    image = image.crop(
        (
            rectangle.start.x,
            rectangle.start.y,
            rectangle.start.x + rectangle.dimensions.width,
            rectangle.start.y + rectangle.dimensions.height,
        )
    )
    # image.save('/tmp/blu/4.png')
    return image

