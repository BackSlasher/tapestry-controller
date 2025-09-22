import PIL.Image
import threading
from .models import Config, load_config
from .geometry import Point, Dimensions, Rectangle
from .image_utils import image_refit, image_crop
from .device import draw, clear


class TapestryController:
    def __init__(self, config: Config):
        self.config = config

    def send_image(self, image: PIL.Image, debug_output_dir: str = None):
        """Send image to devices using a simplified coordinate approach."""
        
        # Step 1: Calculate the bounding box of all screens in millimeters
        device_rects_mm = {}
        for device in self.config.devices:
            device_rects_mm[device] = Rectangle(
                start=Point(x=device.coordinates.x, y=device.coordinates.y),
                dimensions=Dimensions(
                    width=device.detected_dimensions.width,
                    height=device.detected_dimensions.height,
                )
            )
        
        # Find the overall bounding rectangle in millimeters
        bounding_rect_mm = Rectangle.bounding_rectangle(device_rects_mm.values())
        
        # Step 2: Scale the input image to fit the bounding rectangle
        # while maintaining aspect ratio
        scaled_image, mm_to_px_ratio = self._scale_image_to_layout(
            image, bounding_rect_mm.dimensions
        )
        
        if debug_output_dir:
            scaled_image.save(f"{debug_output_dir}/scaled_image.png")
            
        # Step 3: For each device, calculate its position in the scaled image
        # and crop the appropriate section
        threads = []
        for device, rect_mm in device_rects_mm.items():
            # Convert device position from mm to pixels in scaled image
            device_rect_px = Rectangle(
                start=Point(
                    x=int((rect_mm.start.x - bounding_rect_mm.start.x) * mm_to_px_ratio),
                    y=int((rect_mm.start.y - bounding_rect_mm.start.y) * mm_to_px_ratio)
                ),
                dimensions=Dimensions(
                    width=int(rect_mm.dimensions.width * mm_to_px_ratio),
                    height=int(rect_mm.dimensions.height * mm_to_px_ratio)
                )
            )
            
            # Crop the section for this device
            device_image = self._crop_device_section(scaled_image, device_rect_px)
            
            if debug_output_dir:
                device_image.save(f"{debug_output_dir}/device_{device.host}.png")
            
            # Send to device in parallel
            t = threading.Thread(
                target=draw, 
                args=(device.host, device_image, True, device.rotation)
            )
            t.daemon = True
            t.start()
            threads.append(t)
        
        # Wait for all threads to complete
        for t in threads:
            t.join()
    
    def _scale_image_to_layout(self, image: PIL.Image, layout_dimensions: Dimensions):
        """Scale input image to fit the layout dimensions while maintaining aspect ratio."""
        import PIL.ImageOps
        
        # Calculate the best fit scaling
        image_width, image_height = image.size
        layout_width, layout_height = layout_dimensions.width, layout_dimensions.height
        
        # Calculate scale factors for both dimensions
        scale_x = image_width / layout_width
        scale_y = image_height / layout_height
        
        # Use the smaller scale factor to ensure the entire layout fits
        mm_to_px_ratio = min(scale_x, scale_y)
        
        # Calculate the target image size
        target_width = int(layout_width * mm_to_px_ratio)
        target_height = int(layout_height * mm_to_px_ratio)
        
        # Use PIL's fit function to scale and crop the image appropriately
        scaled_image = PIL.ImageOps.fit(
            image, 
            (target_width, target_height), 
            method=PIL.Image.LANCZOS
        )
        
        return scaled_image, mm_to_px_ratio
    
    def _crop_device_section(self, scaled_image: PIL.Image, device_rect_px: Rectangle):
        """Crop a section of the scaled image for a specific device."""
        
        # Calculate crop coordinates
        left = max(0, device_rect_px.start.x)
        top = max(0, device_rect_px.start.y)
        right = min(scaled_image.width, device_rect_px.start.x + device_rect_px.dimensions.width)
        bottom = min(scaled_image.height, device_rect_px.start.y + device_rect_px.dimensions.height)
        
        # Crop the image
        cropped = scaled_image.crop((left, top, right, bottom))
        
        # If the cropped section is smaller than expected (due to edge constraints),
        # pad it with white background to match the expected device dimensions
        expected_width = device_rect_px.dimensions.width  
        expected_height = device_rect_px.dimensions.height
        
        if cropped.size != (expected_width, expected_height):
            # Create a white background of the expected size
            padded_image = PIL.Image.new('RGB', (expected_width, expected_height), 'white')
            
            # Calculate where to paste the cropped section
            paste_x = max(0, -device_rect_px.start.x)
            paste_y = max(0, -device_rect_px.start.y)
            
            padded_image.paste(cropped, (paste_x, paste_y))
            return padded_image
        
        return cropped

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
    def from_config_file(cls, config_file: str) -> 'TapestryController':
        config = load_config(config_file)
        return cls(config)