import argparse
import PIL.Image
import drawing
from epdiy import draw
import math
import threading

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("filename", help="Image to print")
    parser.add_argument("--devices-file", default="devices.yaml")
    return parser.parse_args()


import yaml
from typing import NamedTuple


class AreaDimensions(NamedTuple):
    height: float
    width: float

class FullDimensions(NamedTuple):
    top: float
    bottom: float
    left: float
    right: float

class ScreenType(NamedTuple):
    active_area: AreaDimensions
    bezel: FullDimensions

    def total_dimensions(self) -> AreaDimensions:
        return AreaDimensions(
            height=self.bezel.top+self.active_area.height+self.bezel.bottom,
            width=self.bezel.left+self.active_area.width+self.bezel.right,
        )

class Coordinates(NamedTuple):
    x: int
    y: int

class Device(NamedTuple):
    host: str
    screen_type: ScreenType
    coordinates: Coordinates


class DeviceCollection(NamedTuple):
    devices: list[Device]

from PIL import Image, ImageDraw, ImageFont

class Config(NamedTuple):
    screen_types: dict[str, ScreenType]
    devices: list[Device]

    def to_rectangles(self):
        device_rectangles = {}
        for device in self.devices:
            start = drawing.Point(x=device.coordinates.x,y=device.coordinates.y)
            dimensions=drawing.Dimensions(
                width=device.screen_type.total_dimensions().width,
                height=device.screen_type.total_dimensions().height,
            )
            device_rectangles[device] = drawing.Rectangle(
                start=start,
                dimensions=dimensions,
            )
        return device_rectangles

    def draw_rectangles(self, filename):
        device_rectangles = self.to_rectangles()
        bounding_rectangle = drawing.Rectangle.bounding_rectangle(device_rectangles.values())
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
    screen_types = {}
    for s_name, s in y['screen_types'].items():
        active_area = AreaDimensions(
            height=s['active_area']['height'],
            width=s['active_area']['width'],
        )
        bezel = FullDimensions(
            top=s['bezel']['top'],
            bottom=s['bezel']['bottom'],
            left=s['bezel']['left'],
            right=s['bezel']['right'],
        )
        screen_types[s_name] = ScreenType(
            active_area=active_area,
            bezel=bezel,
        )
    devices=[]
    for d in y['devices']:
        devices.append(Device(
            host=d['host'],
            screen_type=screen_types[d['screen_type']],
            coordinates = Coordinates(
                x=d['coordinates']['x'],
                y=d['coordinates']['y'],
            )
        ))
    return Config(
        screen_types=screen_types,
        devices=devices,
    )

def main():
    args = parse_args()
    config = load_config(args.devices_file)

    big_image = PIL.Image.open(args.filename)
    # get complete rectangle
    device_rectangles = {}
    for device in config.devices:
        start = drawing.Point(x=device.coordinates.x,y=device.coordinates.y)
        dimensions=drawing.Dimensions(
            width=device.screen_type.total_dimensions().width,
            height=device.screen_type.total_dimensions().height,
        )
        device_rectangles[device] = drawing.Rectangle(
            start=start,
            dimensions=dimensions,
        )
    # refit image to complete rectangle
    bounding_rectangle = drawing.Rectangle.bounding_rectangle(device_rectangles.values())
    refit_image, px_in_unit = drawing.image_refit(big_image, bounding_rectangle.dimensions)
    refit_image.save("/tmp/blu/a.png")
    # for each device, cut the proper rectangle from the image
    print(bounding_rectangle, px_in_unit)
    config.draw_rectangles("/tmp/blu/ff.png")
    threads = []
    for d,r in device_rectangles.items():
        r = r.ratioed(px_in_unit)
        print(d.host,r)
        cut_image = drawing.image_crop(refit_image, r)
        # send the image to the device
        t = threading.Thread(target=draw,args=(d.host, cut_image, True))
        t.daemon = True
        t.start()
        threads.append(t)
    for t in threads:
        t.join()
        



if __name__ == "__main__":
    main()

