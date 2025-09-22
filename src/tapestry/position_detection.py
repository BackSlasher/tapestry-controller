"""
Image parsing and position detection for QR-based positioning system.
"""

import json
import math
import numpy as np
from PIL import Image
import cv2
from typing import Dict, List, Tuple, NamedTuple, Optional
from .models import Device, Config
from .screen_types import SCREEN_TYPES


class QRPositionData(NamedTuple):
    """Data structure for QR positioning information."""
    hostname: str
    screen_type: str  # screen type from QR code
    center: Tuple[float, float]  # (x, y) in image coordinates
    rotation: float  # degrees
    corners: List[Tuple[float, float]]  # QR code corner positions
    bounding_box: Tuple[float, float, float, float]  # (min_x, min_y, max_x, max_y) of QR code
    screen_width_px: int  # actual screen width from JSON data
    screen_height_px: int  # actual screen height from JSON data
    qr_size_px: int  # expected QR size from JSON data
    screen_corners: List[Tuple[float, float]]  # calculated screen corners in image


def calculate_qr_rotation_from_corners(corners: List[Tuple[float, float]]) -> float:
    """Calculate QR rotation from OpenCV corner points (top-left, top-right, bottom-right, bottom-left)."""
    if len(corners) < 4:
        return 0.0
    
    # OpenCV QRCodeDetector returns corners in this order:
    # 0: top-left, 1: top-right, 2: bottom-right, 3: bottom-left
    top_left = corners[0]
    top_right = corners[1]
    
    # Calculate the angle of the top edge (from top-left to top-right)
    dx = top_right[0] - top_left[0]
    dy = top_right[1] - top_left[1]
    
    # For a 0° QR code, the top edge should be horizontal (angle = 0°)
    rotation = math.degrees(math.atan2(dy, dx))
    
    # Normalize to common rotation angles and fix sign convention
    # Your expected rotations: big=180°, small_left=90°, small_right=0°
    # Adjust rotation to match expected convention
    if rotation < -45:
        rotation += 360  # Convert negative angles to positive equivalent
    
    print(f"QR rotation from corners: top edge angle = {rotation:.1f}°")
    return rotation


def detect_qr_positions(pil_image: Image.Image) -> List[QRPositionData]:
    """
    1. Detect all QR codes in the image
    2. Filter out non-DIGINK ones  
    3. Get rotation from QR code
    4. Calculate screen corners from QR bounding box and JSON data
    """
    
    # Convert PIL image to OpenCV format
    if pil_image.mode != 'RGB':
        pil_image = pil_image.convert('RGB')
    
    np_image = np.array(pil_image)
    cv_image = cv2.cvtColor(np_image, cv2.COLOR_RGB2GRAY)
    
    # Step 1: Detect all QR codes
    qcd = cv2.QRCodeDetector()
    retval, decoded_info, points, straight_qrcode = qcd.detectAndDecodeMulti(cv_image)
    
    if not retval or not decoded_info:
        print("No QR codes detected by cv2")
        return []
    
    print(f"cv2 detected {len(decoded_info)} QR codes")
    
    position_data = []
    
    # Process each detected QR code
    for i in range(len(decoded_info)):
        try:
            # Step 2: Filter out non-DIGINK ones
            data = decoded_info[i]
            if not data or not data.startswith('DIGINK:'):
                print(f"QR {i}: Not a DIGINK QR code: {data}")
                continue
            
            # Parse DIGINK JSON data
            json_str = data[7:]  # Remove "DIGINK:" prefix
            try:
                qr_json = json.loads(json_str)
            except json.JSONDecodeError as e:
                print(f"QR {i}: Invalid JSON data: {e}")
                continue
            
            # Extract data from JSON
            ip = qr_json['ip']
            screen_type = qr_json['screen_type'] 
            screen_width_px = qr_json['screen_width_px']
            screen_height_px = qr_json['screen_height_px']
            qr_size_px = qr_json['qr_size_px']
            
            # Get corner positions for this QR code
            qr_corners = points[i].reshape(-1, 2)
            if len(qr_corners) < 4:
                print(f"QR {i} ({ip}): Insufficient corners: {len(qr_corners)}")
                continue
            
            corners = [(float(x), float(y)) for x, y in qr_corners]
            
            # Calculate center
            center_x = float(np.mean(qr_corners[:, 0]))
            center_y = float(np.mean(qr_corners[:, 1]))
            center = (center_x, center_y)
            
            # Step 3: Get rotation from QR code
            rotation = calculate_qr_rotation_from_corners(corners)
            
            # Map raw rotation to standard orientations (0°, 90°, 180°, 270°)
            normalized = rotation % 360
            if normalized < 45 or normalized >= 315:
                rotation = 0
            elif 45 <= normalized < 135:
                rotation = 90
            elif 135 <= normalized < 225:
                rotation = 180
            else:  # 225 <= normalized < 315
                rotation = 270
            
            # Step 4: Calculate screen corners from QR bounding box and JSON data
            
            # Step 4.1: Measure bounding box of QR code
            min_x = min(c[0] for c in corners)
            max_x = max(c[0] for c in corners)
            min_y = min(c[1] for c in corners)
            max_y = max(c[1] for c in corners)
            bounding_box = (min_x, min_y, max_x, max_y)
            
            # Measure actual QR size in image
            qr_width_img = max_x - min_x
            qr_height_img = max_y - min_y
            qr_size_img = (qr_width_img + qr_height_img) / 2
            
            # Step 4.2: Get qr_size_px from QR code (already extracted from JSON)
            # Step 4.3: Calculate pixel ratio
            pixel_ratio = qr_size_img / qr_size_px
            print(f"QR {i} ({ip}): QR size in image: {qr_size_img:.1f}px, expected: {qr_size_px}px, ratio: {pixel_ratio:.4f}")
            
            # Step 4.4: Calculate screen corners using ratio and screen dimensions
            screen_width_img = screen_width_px * pixel_ratio  
            screen_height_img = screen_height_px * pixel_ratio
            
            # Calculate screen corners relative to QR center
            screen_corners = [
                (center_x - screen_width_img/2, center_y - screen_height_img/2),  # top-left
                (center_x + screen_width_img/2, center_y - screen_height_img/2),  # top-right  
                (center_x + screen_width_img/2, center_y + screen_height_img/2),  # bottom-right
                (center_x - screen_width_img/2, center_y + screen_height_img/2)   # bottom-left
            ]
            
            # Create position data
            qr_data = QRPositionData(
                hostname=ip,
                screen_type=screen_type,
                center=center,
                rotation=rotation,
                corners=corners,
                bounding_box=bounding_box,
                screen_width_px=screen_width_px,
                screen_height_px=screen_height_px,
                qr_size_px=qr_size_px,
                screen_corners=screen_corners
            )
            
            position_data.append(qr_data)
            
            print(f"QR {i}: {ip} ({screen_type}) at ({center_x:.1f},{center_y:.1f}), rotation: {rotation}°")
            print(f"  Screen: {screen_width_px}x{screen_height_px}px → {screen_width_img:.1f}x{screen_height_img:.1f}px in image")
            
        except Exception as e:
            print(f"Error processing QR code {i}: {e}")
            continue
    
    return position_data


# Old corner dot detection function removed - now using calculated corners from QR JSON data


def calculate_physical_positions_from_qr(position_data: List[QRPositionData], config: Config) -> Dict[str, Dict]:
    """Calculate physical screen positions using detected corner lines."""
    if not position_data:
        return {}
    
    print(f"\n=== Corner-Based Position Calculation for {len(position_data)} screens ===")
    
    # For each QR code, try to detect screen corners from diagonal lines
    screen_data = []
    
    for data in position_data:
        print(f"Analyzing screen boundaries for {data.hostname}...")
        
        qr_center = data.center
        detected_corners = None
        
        # Use the calculated screen corners from QR JSON data
        screen_corner_positions = data.screen_corners
        
        if screen_corner_positions and len(screen_corner_positions) >= 4:
            print(f"  Using calculated screen corners from QR data")
            
            # Build screen box from calculated corners
            min_x = min(c[0] for c in screen_corner_positions)
            max_x = max(c[0] for c in screen_corner_positions) 
            min_y = min(c[1] for c in screen_corner_positions)
            max_y = max(c[1] for c in screen_corner_positions)
            
            screen_width_px = max_x - min_x
            screen_height_px = max_y - min_y
            screen_top_left = (min_x, min_y)
            
            print(f"  Screen box: ({min_x:.0f},{min_y:.0f}) to ({max_x:.0f},{max_y:.0f}), size: {screen_width_px:.0f}x{screen_height_px:.0f}px")
        else:
            print(f"  No screen corners calculated for {data.hostname} - skipping")
            continue
        
        screen_data.append({
            'hostname': data.hostname,
            'screen_type': data.screen_type,
            'rotation': data.rotation,
            'qr_center': qr_center,
            'screen_top_left': screen_top_left,
            'screen_width_px': screen_width_px,
            'screen_height_px': screen_height_px
        })
    
    if not screen_data:
        return {}
    
    # Step 2.6: Understand positioning and rotation using the detected boxes
    # Convert to layout coordinates using a reasonable scale
    avg_screen_size = sum(s['screen_width_px'] for s in screen_data) / len(screen_data)
    typical_screen_size_mm = 150  # Assume average screen is ~150mm wide
    scale_factor = typical_screen_size_mm / avg_screen_size
    
    print(f"Average screen size: {avg_screen_size:.0f}px → {typical_screen_size_mm}mm, scale: {scale_factor:.4f} mm/px")
    
    # Step 3.1: Translate so that there are no negative coordinates
    min_x = min(s['screen_top_left'][0] for s in screen_data)
    min_y = min(s['screen_top_left'][1] for s in screen_data)
    
    positions = {}
    margin = 20  # Add small margin around layout
    
    for screen in screen_data:
        # Translate coordinates to remove negatives, then scale and add margin
        translated_x = screen['screen_top_left'][0] - min_x
        translated_y = screen['screen_top_left'][1] - min_y
        
        layout_x = translated_x * scale_factor + margin
        layout_y = translated_y * scale_factor + margin
        
        positions[screen['hostname']] = {
            'x': layout_x,
            'y': layout_y,
            'rotation': screen['rotation'],
            'screen_type': screen['screen_type'],
            'scale_factor': scale_factor,
            'detected_width': screen['screen_width_px'] * scale_factor,
            'detected_height': screen['screen_height_px'] * scale_factor
        }
        
        print(f"  FINAL {screen['hostname']}: ({layout_x:.0f}, {layout_y:.0f}) - from detected screen box")
    
    return positions


def calculate_physical_positions(position_data: List[QRPositionData], config: Config, pil_image: Image.Image = None) -> Dict[str, Dict]:
    """Calculate physical screen positions using cv2 QR detection and JSON data."""
    # Use the new JSON-based implementation (pil_image parameter kept for backward compatibility but unused)
    return calculate_physical_positions_from_qr(position_data, config)


def generate_updated_config(original_config: Config, positions: Dict[str, Dict]) -> Dict:
    """Generate updated configuration with new device positions."""
    
    # Create updated configuration dictionary
    devices = []
    
    for ip, pos_data in positions.items():
        device_config = {
            'host': ip,
            'screen_type': pos_data['screen_type'],
            'coordinates': {
                'x': int(pos_data['x']),
                'y': int(pos_data['y'])
            },
            'rotation': int(pos_data['rotation']),
            'detected_dimensions': {
                'width': int(pos_data['detected_width']),
                'height': int(pos_data['detected_height'])
            }
        }
        devices.append(device_config)
    
    config = {
        'devices': devices
    }
    
    # No screen_types data to preserve - now just strings
    
    return config