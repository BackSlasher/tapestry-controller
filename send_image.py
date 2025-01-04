import argparse
import PIL.Image
import drawing
from epdiy import draw

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
    rotation: int
    coordinates: Coordinates


class DeviceCollection(NamedTuple):
    devices: list[Device]

class Config(NamedTuple):
    screen_types: dict[str, ScreenType]
    devices: list[Device]

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
            rotation=d['rotation'],
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
        rotation_deg=device.rotation
        device_rectangles[device] = drawing.Rectangle(
            start=start,
            dimensions=dimensions,
            rotation_deg=rotation_deg,
        )
    # refit image to complete rectangle
    bounding_rectangle = drawing.Rectangle.bounding_rectangle(device_rectangles.values())
    refit_image = drawing.image_refit(big_image, bounding_rectangle.dimensions)
    # for each device, cut the proper rectangle from the image
    for device, rectangle in device_rectangles.items():
        cut_image = drawing.image_crop(refit_image, rectangle)
        # send the image to the device
        draw(device.host, cut_image, True)
        



if __name__ == "__main__":
    main()

