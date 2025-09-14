#!/usr/bin/env python3
"""
Comprehensive positioning validation script.

Takes a debug photo, runs the positioning system, and generates
a visual comparison between the input photo and detected layout
for validation purposes.
"""

import sys
import os
import argparse
from pathlib import Path

# Add the src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from digink.position_detection import detect_qr_positions, calculate_physical_positions
from digink.models import Config
from digink.screen_types import SCREEN_TYPES
from PIL import Image, ImageDraw, ImageFont
import math

def draw_layout_diagram(positions, output_path):
    """Draw a layout diagram from positioning results."""
    if not positions:
        print("No positions to draw")
        return
    
    # Calculate bounds
    margin = 50
    min_x = min(pos['x'] for pos in positions.values()) - margin
    min_y = min(pos['y'] for pos in positions.values()) - margin
    max_x = max(pos['x'] + SCREEN_TYPES[pos['screen_type']].active_area.width 
                for pos in positions.values()) + margin
    max_y = max(pos['y'] + SCREEN_TYPES[pos['screen_type']].active_area.height 
                for pos in positions.values()) + margin
    
    # Create image
    width = int(max_x - min_x)
    height = int(max_y - min_y)
    img = Image.new('RGB', (width, height), 'white')
    draw = ImageDraw.Draw(img)
    
    # Try to load a font
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
    except:
        font = ImageFont.load_default()
    
    # Draw each screen
    for ip, pos in positions.items():
        screen_type = SCREEN_TYPES[pos['screen_type']]
        
        # Calculate screen rectangle (adjusted for image coordinates)
        screen_x = pos['x'] - min_x
        screen_y = pos['y'] - min_y
        screen_w = screen_type.active_area.width
        screen_h = screen_type.active_area.height
        
        # Draw screen rectangle
        draw.rectangle([screen_x, screen_y, screen_x + screen_w, screen_y + screen_h], 
                      outline='black', fill='lightgray', width=2)
        
        # Draw orientation indicator (caret pointing up)
        center_x = screen_x + screen_w // 2
        center_y = screen_y + screen_h // 2
        
        # Calculate rotated caret position
        rotation_rad = math.radians(pos['rotation'])
        
        # Caret pointing up (before rotation)
        caret_size = 15
        points = [
            (0, -caret_size),   # top point
            (-caret_size//2, caret_size//2),  # bottom left
            (caret_size//2, caret_size//2)    # bottom right
        ]
        
        # Rotate and translate points
        rotated_points = []
        for px, py in points:
            # Rotate
            rx = px * math.cos(rotation_rad) - py * math.sin(rotation_rad)
            ry = px * math.sin(rotation_rad) + py * math.cos(rotation_rad)
            # Translate to center
            rotated_points.append((center_x + rx, center_y + ry))
        
        # Draw caret
        draw.polygon(rotated_points, fill='red', outline='darkred')
        
        # Draw label with IP
        label = f"{ip}\n{pos['screen_type']}\n{pos['rotation']}°"
        
        # Position label outside the screen
        label_x = screen_x + screen_w + 5
        label_y = screen_y
        
        # Make sure label fits in image
        if label_x + 100 > width:  # rough estimate of label width
            label_x = screen_x - 100
        if label_x < 0:
            label_x = 5
            
        draw.text((label_x, label_y), label, fill='black', font=font)
    
    # Save image
    img.save(output_path)
    print(f"Generated layout diagram: {output_path}")

def validate_positioning(input_photo_path, output_dir=None):
    """Run positioning validation on a debug photo."""
    if output_dir is None:
        output_dir = os.path.dirname(input_photo_path)
    
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)
    
    print(f"=== Positioning Validation ===")
    print(f"Input photo: {input_photo_path}")
    print(f"Output directory: {output_dir}")
    
    # Load image
    try:
        image = Image.open(input_photo_path)
        print(f"Loaded image: {image.size[0]}x{image.size[1]} pixels")
    except Exception as e:
        print(f"Error loading image: {e}")
        return False
    
    # Detect QR positions
    print("\n--- QR Detection ---")
    position_data = detect_qr_positions(image)
    
    if not position_data:
        print("❌ No QR codes detected!")
        return False
    
    print(f"✅ Detected {len(position_data)} QR codes")
    for data in position_data:
        print(f"  {data.hostname} ({data.screen_type}) at ({data.center[0]:.0f},{data.center[1]:.0f}), rotation: {data.rotation:.0f}°")
    
    # Calculate physical positions
    print("\n--- Position Calculation ---")
    config = Config(devices=[])  # Empty config for positioning
    positions = calculate_physical_positions(position_data, config, image)
    
    if not positions:
        print("❌ Position calculation failed!")
        return False
    
    print(f"✅ Calculated positions for {len(positions)} screens")
    for ip, pos in positions.items():
        print(f"  {ip}: ({pos['x']:.0f}, {pos['y']:.0f}), rotation: {pos['rotation']:.0f}°")
    
    # Generate layout diagram
    print("\n--- Layout Generation ---")
    input_name = Path(input_photo_path).stem
    layout_path = output_dir / f"{input_name}_detected_layout.png"
    draw_layout_diagram(positions, layout_path)
    
    # Copy input photo to output directory for comparison
    comparison_path = output_dir / f"{input_name}_input_photo.jpg"
    image.save(comparison_path)
    print(f"Copied input photo: {comparison_path}")
    
    print(f"\n✅ Validation complete!")
    print(f"Compare these files:")
    print(f"  Input: {comparison_path}")
    print(f"  Layout: {layout_path}")
    
    return True

def main():
    parser = argparse.ArgumentParser(description='Validate positioning system with debug photo')
    parser.add_argument('input_photo', help='Path to input photo with QR codes')
    parser.add_argument('--output-dir', help='Output directory (default: same as input)')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.input_photo):
        print(f"Error: Input photo not found: {args.input_photo}")
        sys.exit(1)
    
    success = validate_positioning(args.input_photo, args.output_dir)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()