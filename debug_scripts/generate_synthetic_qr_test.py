#!/usr/bin/env python3
"""
Generate synthetic QR test image to verify OpenCV detection capabilities.

This script creates a synthetic black and white image with QR codes positioned
to match the physical layout from test photos, then tests cv2.QRCodeDetector
to verify it can detect all QR codes with correct rotations.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import cv2
import numpy as np
from PIL import Image, ImageDraw
import qrcode
from digink.position_detection import detect_qr_positions

def create_synthetic_test_image():
    """Create synthetic test image with QR codes matching physical layout."""
    
    # Create 800x600 white background
    width, height = 800, 600
    img = Image.new('RGB', (width, height), 'white')
    draw = ImageDraw.Draw(img)
    
    # QR code configurations matching physical layout
    qr_configs = [
        {
            'data': 'DIGINK:10.42.0.166:waveshare_7in5_v2',
            'position': (400, 200),  # center position
            'size': 120,
            'rotation': 180  # big screen
        },
        {
            'data': 'DIGINK:10.42.0.167:waveshare_2in66',
            'position': (250, 350),  # left small screen
            'size': 80,
            'rotation': 90
        },
        {
            'data': 'DIGINK:10.42.0.168:waveshare_2in66',
            'position': (550, 350),  # right small screen
            'size': 80,
            'rotation': 0
        }
    ]
    
    for config in qr_configs:
        # Generate QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=4,
            border=2,
        )
        qr.add_data(config['data'])
        qr.make(fit=True)
        
        qr_img = qr.make_image(fill_color="black", back_color="white")
        
        # Resize to target size
        qr_img = qr_img.resize((config['size'], config['size']), Image.LANCZOS)
        
        # Rotate if needed
        if config['rotation'] != 0:
            qr_img = qr_img.rotate(config['rotation'], expand=True)
        
        # Calculate paste position (center the QR code)
        qr_w, qr_h = qr_img.size
        paste_x = config['position'][0] - qr_w // 2
        paste_y = config['position'][1] - qr_h // 2
        
        # Paste onto main image
        img.paste(qr_img, (paste_x, paste_y))
        
        print(f"Added QR: {config['data'].split(':')[1]} at ({paste_x}, {paste_y}) "
              f"size {qr_w}x{qr_h}, rotation {config['rotation']}°")
    
    return img

def run_cv2_detection(img):
    """Test OpenCV QR detection on the synthetic image."""
    print("\n=== Testing cv2.QRCodeDetector ===")
    
    # Test our detection function
    position_data = detect_qr_positions(img)
    
    print(f"\nDetection Results:")
    print(f"Found {len(position_data)} QR codes")
    
    for i, data in enumerate(position_data):
        print(f"QR {i+1}: {data.hostname} ({data.screen_type})")
        print(f"  Center: ({data.center[0]:.1f}, {data.center[1]:.1f})")
        print(f"  Rotation: {data.rotation:.1f}°")
        print(f"  Reference size: {data.reference_size:.1f}px")
    
    return len(position_data) == 3

def main():
    """Generate synthetic test and verify detection."""
    output_dir = "./debug_scripts"
    os.makedirs(output_dir, exist_ok=True)
    
    print("Generating synthetic QR test image...")
    img = create_synthetic_test_image()
    
    # Save the synthetic image
    synthetic_path = os.path.join(output_dir, "synthetic_qr_test.png")
    img.save(synthetic_path)
    print(f"Saved synthetic test image: {synthetic_path}")
    
    # Test detection
    success = test_cv2_detection(img)
    
    if success:
        print("\n✅ SUCCESS: cv2.QRCodeDetector detected all 3 QR codes!")
    else:
        print("\n❌ FAILED: cv2.QRCodeDetector did not detect all QR codes")
    
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)