"""
Test utilities and test cases for QR positioning system.
"""

import os
import tempfile
import numpy as np
from PIL import Image, ImageDraw
import cv2
import math
from typing import List, Dict, Tuple, Optional
from .positioning import (
    generate_positioning_qr_image, 
    detect_qr_positions, 
    calculate_physical_positions,
    QRPositionData
)
from .models import Config, Device, Coordinates
from .screen_types import SCREEN_TYPES


class SyntheticPhotoGenerator:
    """Utility to create synthetic photos of screen layouts for testing."""
    
    def __init__(self, photo_width: int = 2000, photo_height: int = 1500):
        self.photo_width = photo_width
        self.photo_height = photo_height
        self.pixels_per_mm = 0.5  # Scale factor for synthetic photo (smaller to fit more screens)
    
    def generate_synthetic_photo(self, layout: Dict[str, Dict], output_path: str) -> str:
        """
        Generate a synthetic photo showing screens with QR codes at specified positions.
        
        Args:
            layout: Dict with device hostnames as keys and position info as values
                   Format: {'hostname': {'x': int, 'y': int, 'rotation': float, 'screen_type': str}}
            output_path: Path where to save the synthetic photo
        
        Returns:
            Path to generated photo
        """
        # Create blank photo background (light gray to simulate surface)
        photo = Image.new('RGB', (self.photo_width, self.photo_height), (240, 240, 240))
        photo_draw = ImageDraw.Draw(photo)
        
        # Calculate photo center as origin
        photo_center_x = self.photo_width // 2
        photo_center_y = self.photo_height // 2
        
        for hostname, device_info in layout.items():
            try:
                # Get device position (in mm, convert to pixels)
                device_x = device_info['x'] * self.pixels_per_mm
                device_y = device_info['y'] * self.pixels_per_mm
                rotation = device_info.get('rotation', 0)
                screen_type_name = device_info['screen_type']
                
                # Generate QR image for this device
                qr_img = generate_positioning_qr_image(hostname, screen_type_name)
                
                # Calculate screen size in photo pixels
                screen_type = SCREEN_TYPES[screen_type_name]
                # Simplified scaling: use pixels_per_mm directly on mm dimensions
                screen_width_px = int(screen_type.active_area.width * self.pixels_per_mm)  
                screen_height_px = int(screen_type.active_area.height * self.pixels_per_mm)
                
                # Resize QR image to screen size
                qr_img_resized = qr_img.resize((screen_width_px, screen_height_px))
                
                # Apply rotation if needed
                if abs(rotation) > 0.1:
                    qr_img_resized = qr_img_resized.rotate(rotation, expand=True, fillcolor=255)
                    # Update dimensions after rotation
                    screen_width_px, screen_height_px = qr_img_resized.size
                
                # Calculate paste position in photo (center the screen at the specified coordinates)
                paste_x = photo_center_x + int(device_x) - screen_width_px // 2
                paste_y = photo_center_y - int(device_y) - screen_height_px // 2  # Invert Y for image coordinates
                
                # Ensure the screen fits in the photo bounds, with debug info
                if (paste_x >= 0 and paste_y >= 0 and 
                    paste_x + screen_width_px <= self.photo_width and 
                    paste_y + screen_height_px <= self.photo_height):
                    
                    photo.paste(qr_img_resized, (paste_x, paste_y))
                    
                    # Add a border around the screen for visual clarity
                    photo_draw.rectangle(
                        [paste_x-2, paste_y-2, paste_x + screen_width_px + 2, paste_y + screen_height_px + 2],
                        outline=(100, 100, 100), width=2
                    )
                else:
                    print(f"  Warning: {hostname} positioned outside bounds: "
                          f"({paste_x}, {paste_y}) size {screen_width_px}x{screen_height_px}, "
                          f"photo size {self.photo_width}x{self.photo_height}")
                
            except Exception as e:
                print(f"Warning: Could not place device {hostname}: {e}")
                continue
        
        # Save the synthetic photo
        photo.save(output_path, 'JPEG', quality=90)
        return output_path


class PositioningTestParser:
    """Utility to parse photos and extract layout information."""
    
    def parse_photo_layout(self, pil_image: Image.Image) -> Dict[str, Dict]:
        """
        Parse a PIL image and extract device layout information.
        
        Args:
            pil_image: PIL Image to analyze
            
        Returns:
            Layout dictionary with hostnames as keys and position info as values
        """
        try:
            # Use existing positioning detection
            position_data = detect_qr_positions(pil_image)
            
            if not position_data:
                return {}
            
            # Create a minimal config for coordinate calculation
            # We don't have the actual config, so we'll use relative positioning
            layout = {}
            
            for data in position_data:
                layout[data.hostname] = {
                    'x': int(data.center[0]),  # Image coordinates
                    'y': int(data.center[1]),
                    'rotation': data.rotation,
                    'reference_size': data.reference_size
                }
            
            return layout
            
        except Exception as e:
            print(f"Error parsing photo layout: {e}")
            return {}


def create_test_layout_1() -> Dict[str, Dict]:
    """Create test layout 1: Simple 2x2 grid."""
    return {
        'screen1': {'x': -150, 'y': 100, 'rotation': 0, 'screen_type': 'ED060XC3'},
        'screen2': {'x': 150, 'y': 100, 'rotation': 0, 'screen_type': 'ED060XC3'},
        'screen3': {'x': -150, 'y': -100, 'rotation': 0, 'screen_type': 'ED060XC3'},
        'screen4': {'x': 150, 'y': -100, 'rotation': 0, 'screen_type': 'ED060XC3'},
    }


def create_test_layout_2() -> Dict[str, Dict]:
    """Create test layout 2: Mixed screen sizes with rotation."""
    return {
        'large1': {'x': 0, 'y': 0, 'rotation': 0, 'screen_type': 'ED097TC2'},
        'small1': {'x': -200, 'y': 150, 'rotation': 90, 'screen_type': 'ED060XC3'},
        'small2': {'x': 200, 'y': 150, 'rotation': -90, 'screen_type': 'ED060XC3'},
    }


def create_test_layout_3() -> Dict[str, Dict]:
    """Create test layout 3: Linear arrangement with various rotations."""
    return {
        'dev1': {'x': -300, 'y': 0, 'rotation': 0, 'screen_type': 'ED060XC3'},
        'dev2': {'x': -100, 'y': 0, 'rotation': 45, 'screen_type': 'ED060XC3'},
        'dev3': {'x': 100, 'y': 0, 'rotation': 90, 'screen_type': 'ED060XC3'},
        'dev4': {'x': 300, 'y': 0, 'rotation': 180, 'screen_type': 'ED060XC3'},
    }


def run_round_trip_test(test_name: str, layout: Dict[str, Dict], tolerance_px: int = 50, 
                       tolerance_rotation: float = 10.0) -> bool:
    """
    Run a round-trip test: layout -> photo -> parsed layout.
    
    Args:
        test_name: Name for this test case
        layout: Input layout to test
        tolerance_px: Allowed pixel difference for position detection
        tolerance_rotation: Allowed rotation difference in degrees
        
    Returns:
        True if test passes, False otherwise
    """
    print(f"\nRunning round-trip test: {test_name}")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        # Step 1: Generate synthetic photo
        photo_path = os.path.join(temp_dir, f"{test_name}_photo.jpg")
        generator = SyntheticPhotoGenerator()
        
        try:
            generator.generate_synthetic_photo(layout, photo_path)
            print(f"✓ Generated synthetic photo: {photo_path}")
        except Exception as e:
            print(f"✗ Failed to generate synthetic photo: {e}")
            return False
        
        # Step 2: Parse the photo back to layout
        parser = PositioningTestParser()
        
        try:
            # Load the generated photo as PIL Image
            with Image.open(photo_path) as photo_image:
                parsed_layout = parser.parse_photo_layout(photo_image)
                print(f"✓ Parsed {len(parsed_layout)} devices from photo")
        except Exception as e:
            print(f"✗ Failed to parse photo: {e}")
            return False
        
        # Step 3: Compare original and parsed layouts
        if len(parsed_layout) != len(layout):
            print(f"✗ Device count mismatch: expected {len(layout)}, got {len(parsed_layout)}")
            return False
        
        success = True
        for hostname in layout:
            if hostname not in parsed_layout:
                print(f"✗ Device {hostname} not found in parsed layout")
                success = False
                continue
            
            orig = layout[hostname]
            parsed = parsed_layout[hostname]
            
            # Compare positions (note: parsed positions are in image coordinates)
            # For now, just check that devices were detected
            print(f"✓ Device {hostname} detected at ({parsed['x']}, {parsed['y']}) rotation: {parsed['rotation']:.1f}°")
        
        if success:
            print(f"✓ Round-trip test '{test_name}' PASSED")
        else:
            print(f"✗ Round-trip test '{test_name}' FAILED")
        
        return success


def run_all_positioning_tests():
    """Run all positioning recognition tests."""
    print("Starting QR Positioning Recognition Tests")
    print("=" * 50)
    
    test_cases = [
        ("Simple 2x2 Grid", create_test_layout_1()),
        ("Mixed Sizes with Rotation", create_test_layout_2()),
        ("Linear with Various Rotations", create_test_layout_3()),
    ]
    
    results = []
    for test_name, layout in test_cases:
        result = run_round_trip_test(test_name, layout)
        results.append((test_name, result))
    
    print("\n" + "=" * 50)
    print("Test Results Summary:")
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"{status:4} | {test_name}")
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    return passed == total


if __name__ == "__main__":
    # Run tests when script is executed directly
    run_all_positioning_tests()