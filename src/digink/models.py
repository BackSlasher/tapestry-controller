from typing import NamedTuple
import yaml
from PIL import Image, ImageDraw, ImageFont
from .geometry import Point, Dimensions, Rectangle
from .screen_types import ScreenType, SCREEN_TYPES


class Coordinates(NamedTuple):
    x: int
    y: int


class Device(NamedTuple):
    host: str
    screen_type: ScreenType
    coordinates: Coordinates


class Config(NamedTuple):
    devices: list[Device]

    def to_rectangles(self):
        device_rectangles = {}
        for device in self.devices:
            start = Point(x=device.coordinates.x,y=device.coordinates.y)
            dimensions=Dimensions(
                width=device.screen_type.total_dimensions().width,
                height=device.screen_type.total_dimensions().height,
            )
            device_rectangles[device] = Rectangle(
                start=start,
                dimensions=dimensions,
            )
        return device_rectangles

    def draw_rectangles(self, filename):
        device_rectangles = self.to_rectangles()
        bounding_rectangle = Rectangle.bounding_rectangle(device_rectangles.values())
        background_image = Image.new('RGB', (int(bounding_rectangle.dimensions.width), int(bounding_rectangle.dimensions.height)), (0,0,0))
        for device, rectangle in device_rectangles.items():
            # Create a blank image with the specified size
            width, height = int(rectangle.dimensions.width), int(rectangle.dimensions.height)
            print("aaaa", width, height)
            foreground_image = Image.new('RGB', (width, height), (255, 255, 255))
            # Set the font size and style
            font_size = 16
            font_style = 'Roboto-Black'
            font = ImageFont.truetype(font_style, font_size)

            text = device.host
            draw = ImageDraw.Draw(foreground_image)
            text_width = draw.textlength(text, font=font)
            text_height = font_size
            text_x = (width - text_width) / 2
            text_y = (height - text_height) / 2
            draw.text((text_x, text_y), text, font=font, fill=(0, 0, 0))

            x = int(rectangle.start.x)
            y = int(rectangle.start.y)
            
            print("bbbb", x,y)
            background_image.paste(foreground_image, (x, y))
        background_image.save(filename)


def load_config(devices_file):
    with open(devices_file, "r") as f:
        y = yaml.safe_load(f)
    
    devices = []
    for d in y['devices']:
        screen_type_name = d['screen_type']
        if screen_type_name not in SCREEN_TYPES:
            raise ValueError(f"Unknown screen type: {screen_type_name}")
        
        devices.append(Device(
            host=d['host'],
            screen_type=SCREEN_TYPES[screen_type_name],
            coordinates=Coordinates(
                x=d['coordinates']['x'],
                y=d['coordinates']['y'],
            )
        ))
    
    return Config(devices=devices)