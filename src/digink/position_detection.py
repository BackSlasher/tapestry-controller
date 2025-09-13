"""
Image parsing and position detection for QR-based positioning system.
"""

import numpy as np
from PIL import Image
import cv2
import math
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
    reference_size: float  # size of reference element in pixels
    screen_corners: Optional[List[Tuple[float, float]]]  # Not used in cv2-only approach


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
    """Detect QR codes using OpenCV QRCodeDetector with single detection call."""
    import numpy as np
    
    # Convert PIL image to OpenCV format
    if pil_image.mode != 'RGB':
        pil_image = pil_image.convert('RGB')
    
    np_image = np.array(pil_image)
    img = cv2.cvtColor(np_image, cv2.COLOR_RGB2GRAY)
    
    # Single call to OpenCV QRCodeDetector
    qcd = cv2.QRCodeDetector()
    retval, decoded_info, points, straight_qrcode = qcd.detectAndDecodeMulti(img)
    
    if not retval or not decoded_info:
        print("No QR codes detected by OpenCV")
        return []
    
    print(f"OpenCV detected {len(decoded_info)} QR codes")
    
    position_data = []
    
    # Iterate over the first dimension of points to get every QR code
    for i in range(len(decoded_info)):
        try:
            data = decoded_info[i]
            if not data or not data.startswith('DIGINK:'):
                print(f"QR {i}: Invalid data format: {data}")
                continue
                
            # Parse QR data: DIGINK:IP:SCREEN_TYPE
            parts = data.split(':')
            if len(parts) != 3:
                print(f"QR {i}: Invalid data parts: {parts}")
                continue
                
            ip = parts[1]
            screen_type = parts[2]
            
            # Get corner positions for this QR code
            # OpenCV returns corners in order: top-left, top-right, bottom-right, bottom-left
            qr_corners = points[i].reshape(-1, 2)
            corners = [(float(x), float(y)) for x, y in qr_corners]
            
            if len(corners) < 4:
                print(f"QR {i} ({ip}): Insufficient corners: {len(corners)}")
                continue
            
            # Calculate center
            center_x = float(np.mean(qr_corners[:, 0]))
            center_y = float(np.mean(qr_corners[:, 1]))
            center = (center_x, center_y)
            
            # Calculate rotation from corner positions
            rotation = calculate_qr_rotation_from_corners(corners)
            
            # Calculate QR code dimensions for reference
            dx = corners[1][0] - corners[0][0]  # top edge
            dy = corners[1][1] - corners[0][1]
            qr_width_px = math.sqrt(dx*dx + dy*dy)
            
            dx = corners[3][0] - corners[0][0]  # left edge
            dy = corners[3][1] - corners[0][1]
            qr_height_px = math.sqrt(dx*dx + dy*dy)
            
            reference_size = (qr_width_px + qr_height_px) / 2
            
            # Create position data
            qr_data = QRPositionData(
                hostname=ip,
                screen_type=screen_type,
                center=center,
                rotation=rotation,
                corners=corners,
                reference_size=reference_size,
                screen_corners=None  # Not used in cv2-only approach
            )
            
            position_data.append(qr_data)
            
            print(f"QR {i}: {ip} ({screen_type}) at ({center_x:.1f},{center_y:.1f}), rotation: {rotation:.1f}°")
            
        except Exception as e:
            print(f"Error processing QR code {i}: {e}")
            continue
    
    return position_data


def calculate_physical_positions_from_qr(position_data: List[QRPositionData], config: Config) -> Dict[str, Dict]:
    """Calculate physical screen positions directly from QR code corner information."""
    if not position_data:
        return {}
    
    print(f"\n=== QR-Based Direct Position Calculation for {len(position_data)} screens ===")
    
    screen_positions = []
    
    for data in position_data:
        if data.screen_type not in SCREEN_TYPES:
            print(f"Warning: Unknown screen type {data.screen_type} for {data.hostname}")
            continue
            
        screen_type = SCREEN_TYPES[data.screen_type]
        
        # Get QR corner positions (OpenCV order: top-left, top-right, bottom-right, bottom-left)
        qr_corners = data.corners
        if len(qr_corners) < 4:
            print(f"Warning: Insufficient corners for {data.hostname}")
            continue
        
        # Calculate QR dimensions in pixels from corners
        qr_tl = qr_corners[0]  # top-left
        qr_tr = qr_corners[1]  # top-right
        qr_br = qr_corners[2]  # bottom-right  
        qr_bl = qr_corners[3]  # bottom-left
        
        # QR width and height in pixels
        qr_width_px = math.sqrt((qr_tr[0] - qr_tl[0])**2 + (qr_tr[1] - qr_tl[1])**2)
        qr_height_px = math.sqrt((qr_bl[0] - qr_tl[0])**2 + (qr_bl[1] - qr_tl[1])**2)
        
        # Assume QR code takes up a specific portion of the screen (e.g., 75%)
        # and is centered on the screen
        qr_screen_ratio = 0.75
        screen_width_px = qr_width_px / qr_screen_ratio
        screen_height_px = qr_height_px / qr_screen_ratio
        
        # Calculate screen corners from QR center and rotation
        qr_center = data.center
        rotation_rad = math.radians(data.rotation)
        
        # Screen half-dimensions
        half_width = screen_width_px / 2
        half_height = screen_height_px / 2
        
        # Calculate screen corners relative to center, then rotate
        cos_r = math.cos(rotation_rad)
        sin_r = math.sin(rotation_rad)
        
        # Screen corners in local coordinates (relative to center)
        local_corners = [
            (-half_width, -half_height),  # top-left
            (half_width, -half_height),   # top-right  
            (half_width, half_height),    # bottom-right
            (-half_width, half_height)    # bottom-left
        ]
        
        # Rotate and translate to global coordinates
        screen_corners_px = []
        for lx, ly in local_corners:
            # Rotate
            rx = lx * cos_r - ly * sin_r
            ry = lx * sin_r + ly * cos_r
            # Translate
            gx = rx + qr_center[0]
            gy = ry + qr_center[1]
            screen_corners_px.append((gx, gy))
        
        # Calculate scale factor from screen physical dimensions
        screen_width_mm = screen_type.active_area.width
        screen_height_mm = screen_type.active_area.height
        
        scale_x = screen_width_mm / screen_width_px
        scale_y = screen_height_mm / screen_height_px
        scale_factor = (scale_x + scale_y) / 2
        
        # Screen top-left corner in mm
        screen_tl_px = screen_corners_px[0]  # top-left corner
        screen_tl_mm = (screen_tl_px[0] * scale_factor, screen_tl_px[1] * scale_factor)
        
        print(f"Screen {data.hostname} ({data.screen_type}):")
        print(f"  QR: {qr_width_px:.0f}x{qr_height_px:.0f}px at ({qr_center[0]:.0f},{qr_center[1]:.0f})")
        print(f"  Screen: {screen_width_px:.0f}x{screen_height_px:.0f}px → {screen_width_mm}x{screen_height_mm}mm")
        print(f"  Top-left: ({screen_tl_px[0]:.0f},{screen_tl_px[1]:.0f})px → ({screen_tl_mm[0]:.0f},{screen_tl_mm[1]:.0f})mm")
        print(f"  Scale: {scale_factor:.4f} mm/px")
        
        screen_positions.append({
            'hostname': data.hostname,
            'screen_type': data.screen_type,
            'rotation': data.rotation,
            'screen_tl_mm': screen_tl_mm,
            'scale_factor': scale_factor
        })
    
    # Calculate average scale for consistency
    if screen_positions:
        avg_scale = sum(pos['scale_factor'] for pos in screen_positions) / len(screen_positions)
        print(f"Average scale: {avg_scale:.4f} mm/pixel")
    
    # Find bounding box and normalize coordinates
    if not screen_positions:
        return {}
    
    min_x = min(pos['screen_tl_mm'][0] for pos in screen_positions)
    min_y = min(pos['screen_tl_mm'][1] for pos in screen_positions)
    max_x = max(pos['screen_tl_mm'][0] + SCREEN_TYPES[pos['screen_type']].active_area.width 
                for pos in screen_positions)
    max_y = max(pos['screen_tl_mm'][1] + SCREEN_TYPES[pos['screen_type']].active_area.height 
                for pos in screen_positions)
    
    print(f"Screen bounds: X=[{min_x:.0f}, {max_x:.0f}], Y=[{min_y:.0f}, {max_y:.0f}]")
    
    # Create final position dictionary with normalized coordinates
    positions = {}
    for pos in screen_positions:
        # Normalize to start from (20, 20) with margin
        margin = 20
        final_x = pos['screen_tl_mm'][0] - min_x + margin
        final_y = pos['screen_tl_mm'][1] - min_y + margin
        
        positions[pos['hostname']] = {
            'x': final_x,
            'y': final_y,
            'rotation': pos['rotation'],
            'screen_type': pos['screen_type']
        }
        
        print(f"  FINAL {pos['hostname']}: ({final_x:.0f}, {final_y:.0f}) - direct QR calculation")
    
    return positions


def calculate_physical_positions(position_data: List[QRPositionData], config: Config) -> Dict[str, Dict]:
    """Calculate physical screen positions using cv2 QR detection only."""
    # Use the new cv2-only implementation
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
                'x': pos_data['x'],
                'y': pos_data['y']
            },
            'rotation': pos_data['rotation']
        }
        devices.append(device_config)
    
    config = {
        'devices': devices
    }
    
    # Preserve screen_types if they exist in original config
    if hasattr(original_config, 'screen_types') and original_config.screen_types:
        screen_types = {}
        for name, screen_type in original_config.screen_types.items():
            screen_types[name] = {
                'active_area': {
                    'width': screen_type.active_area.width,
                    'height': screen_type.active_area.height
                },
                'bezel': {
                    'top': screen_type.bezel.top,
                    'bottom': screen_type.bezel.bottom,
                    'left': screen_type.bezel.left,
                    'right': screen_type.bezel.right
                }
            }
        config['screen_types'] = screen_types
    
    return config