import PIL.Image
import threading
from .models import Config, load_config
from .geometry import Point, Dimensions, Rectangle
from .image_utils import image_refit, image_crop
from .device import draw, clear


class DiginkController:
    def __init__(self, config: Config):
        self.config = config

    def send_image(self, image: PIL.Image, debug_output_dir: str = None):
        device_rectangles = {}
        for device in self.config.devices:
            start = Point(x=device.coordinates.x, y=device.coordinates.y)
            # Use detected dimensions from YAML
            dimensions = Dimensions(
                width=device.detected_dimensions.width,
                height=device.detected_dimensions.height,
            )
            device_rectangles[device] = Rectangle(
                start=start,
                dimensions=dimensions,
            )
        
        # Refit image to complete rectangle
        bounding_rectangle = Rectangle.bounding_rectangle(device_rectangles.values())
        refit_result = image_refit(image, bounding_rectangle.dimensions)
        refit_image = refit_result.image
        px_in_unit = refit_result.px_in_unit
        
        if debug_output_dir:
            refit_image.save(f"{debug_output_dir}/refit.png")
            self.config.draw_rectangles(f"{debug_output_dir}/layout.png")
        
        # Send images to devices in parallel
        threads = []
        for device, rectangle in device_rectangles.items():
            r = rectangle.ratioed(px_in_unit)
            cut_image = image_crop(refit_image, r)
            
            t = threading.Thread(target=draw, args=(device.host, cut_image, True, device.rotation))
            t.daemon = True
            t.start()
            threads.append(t)
        
        # Wait for all threads to complete
        for t in threads:
            t.join()

    def clear_devices(self):
        """Clear all device screens."""
        threads = []
        for device in self.config.devices:
            t = threading.Thread(target=clear, args=(device.host,))
            t.daemon = True
            t.start()
            threads.append(t)
        
        # Wait for all threads to complete
        for t in threads:
            t.join()

    @classmethod
    def from_config_file(cls, config_file: str) -> 'DiginkController':
        config = load_config(config_file)
        return cls(config)