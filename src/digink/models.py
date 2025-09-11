from typing import NamedTuple
import yaml
from PIL import Image, ImageDraw, ImageFont
from .geometry import Point, Dimensions, Rectangle
from .screen_types import ScreenType, SCREEN_TYPES

# Import PIL modules unconditionally to fail early if missing dependencies
from PIL import _imagingft  # This will fail immediately if FreeType support is missing


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

    def _generate_layout_image(self, overlay_image=None, overlay_px_in_unit=None):
        """Generate the layout visualization image with optional overlay."""
        device_rectangles = self.to_rectangles()
        bounding_rectangle = Rectangle.bounding_rectangle(device_rectangles.values())
        background_image = Image.new('RGB', (int(bounding_rectangle.dimensions.width), int(bounding_rectangle.dimensions.height)), (0,0,0))
        
        # If overlay image is provided, show it first (faded for non-screen areas)
        if overlay_image and overlay_px_in_unit:
            # Resize overlay to fit the layout
            overlay_width = int(bounding_rectangle.dimensions.width)
            overlay_height = int(bounding_rectangle.dimensions.height)
            overlay_resized = overlay_image.resize((overlay_width, overlay_height))
            
            # Create a faded version for the background
            overlay_faded = overlay_resized.copy()
            overlay_faded.putalpha(128)  # 50% transparency
            
            # Paste faded overlay as background
            if overlay_faded.mode == 'RGBA':
                background_image.paste(overlay_faded, (0, 0), overlay_faded)
            else:
                # Convert to RGBA for blending
                bg_rgba = background_image.convert('RGBA')
                overlay_rgba = overlay_faded.convert('RGBA')
                blended = Image.blend(bg_rgba, overlay_rgba, 0.3)
                background_image = blended.convert('RGB')
        
        for device, rectangle in device_rectangles.items():
            width, height = int(rectangle.dimensions.width), int(rectangle.dimensions.height)
            
            if overlay_image and overlay_px_in_unit:
                # Extract the portion of the image that corresponds to this screen
                r = rectangle.ratioed(overlay_px_in_unit)
                try:
                    # Crop the overlay image for this screen
                    from .image_utils import image_crop
                    screen_image = image_crop(overlay_image, r)
                    # Resize to exact screen dimensions
                    screen_image = screen_image.resize((width, height))
                    foreground_image = screen_image
                except Exception as e:
                    # Fallback to white background if cropping fails
                    print(f"Error cropping image for device {device.host}: {e}")
                    foreground_image = Image.new('RGB', (width, height), (255, 255, 255))
            else:
                # Create a blank white image
                foreground_image = Image.new('RGB', (width, height), (255, 255, 255))
            
            # Add device hostname as overlay text
            try:
                font_size = 16
                try:
                    font = ImageFont.truetype('Roboto-Black', font_size)
                except (OSError, IOError):
                    try:
                        font = ImageFont.truetype('/System/Library/Fonts/Arial.ttf', font_size)
                    except (OSError, IOError):
                        try:
                            font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', font_size)
                        except (OSError, IOError):
                            font = ImageFont.load_default()

                # Create a semi-transparent overlay for text
                text_overlay = Image.new('RGBA', (width, height), (0, 0, 0, 0))
                text_draw = ImageDraw.Draw(text_overlay)
                
                text = device.host
                text_width = text_draw.textlength(text, font=font)
                text_height = font_size
                text_x = (width - text_width) / 2
                text_y = height - text_height - 5  # Bottom of screen
                
                # Draw text background
                text_draw.rectangle([text_x-2, text_y-2, text_x+text_width+2, text_y+text_height+2], 
                                  fill=(0, 0, 0, 180))
                text_draw.text((text_x, text_y), text, font=font, fill=(255, 255, 255, 255))
                
                # Composite text overlay onto screen image
                if foreground_image.mode != 'RGBA':
                    foreground_image = foreground_image.convert('RGBA')
                foreground_image = Image.alpha_composite(foreground_image, text_overlay)
                foreground_image = foreground_image.convert('RGB')
                
            except Exception as e:
                print(f"Error adding text overlay for device {device.host}: {e}")

            x = int(rectangle.start.x)
            y = int(rectangle.start.y)
            
            background_image.paste(foreground_image, (x, y))
        
        return background_image

    def draw_rectangles(self, filename):
        """Save layout visualization to a file."""
        image = self._generate_layout_image()
        image.save(filename)

    def draw_rectangles_to_buffer(self, buffer, overlay_image=None, overlay_px_in_unit=None):
        """Save layout visualization to a buffer with optional overlay."""
        image = self._generate_layout_image(overlay_image, overlay_px_in_unit)
        image.save(buffer, format='PNG')


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