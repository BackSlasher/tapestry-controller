"""
QR-based automatic screen positioning system.
"""

import io
import qrcode
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import cv2
from pyzbar import pyzbar
import math
from typing import Dict, List, Tuple, NamedTuple, Optional
from .models import Device, Config
from .screen_types import SCREEN_TYPES


class QRPositionData(NamedTuple):
    """Data structure for QR positioning information."""
    hostname: str
    center: Tuple[float, float]  # (x, y) in image coordinates
    rotation: float  # degrees
    corners: List[Tuple[float, float]]  # QR code corner positions
    reference_size: float  # size of reference element in pixels


class ReferenceElement(NamedTuple):
    """Reference element for scale and perspective correction."""
    actual_size_mm: float  # known physical size in mm
    pixel_size: float  # measured size in pixels from photo


def generate_positioning_qr_image(hostname: str, screen_type_name: str) -> Image.Image:
    """Generate QR code with reference elements for positioning."""
    screen_type = SCREEN_TYPES[screen_type_name]
    
    # Get screen dimensions in pixels (use device resolution or estimate)
    # For e-ink displays, we'll use a standard DPI estimation
    dpi = 150  # typical e-ink DPI
    width_px = int(screen_type.active_area.width * dpi / 25.4)  # mm to pixels
    height_px = int(screen_type.active_area.height * dpi / 25.4)
    
    # Create base image
    img = Image.new('L', (width_px, height_px), 255)  # White background
    draw = ImageDraw.Draw(img)
    
    # Generate QR code with positioning data
    qr_data = f"DIGINK:{hostname}:{screen_type_name}"
    qr = qrcode.QRCode(
        version=3,  # Size 3 should be readable but not too large
        error_correction=qrcode.constants.ERROR_CORRECT_H,  # High error correction
        box_size=8,  # Increased from 4 to 8 for 2x bigger QR codes
        border=2,
    )
    qr.add_data(qr_data)
    qr.make(fit=True)
    
    # Create QR code image
    qr_img = qr.make_image(fill_color="black", back_color="white")
    
    # Position QR code in center
    qr_width, qr_height = qr_img.size
    qr_x = (width_px - qr_width) // 2
    qr_y = (height_px - qr_height) // 2
    img.paste(qr_img, (qr_x, qr_y))
    
    # Add reference elements for scale and perspective correction
    add_reference_elements(draw, width_px, height_px, screen_type)
    
    # Add hostname text at bottom
    try:
        font_size = min(width_px, height_px) // 20
        font = ImageFont.load_default()  # Use default font for reliability
    except:
        font = None
    
    text = f"{hostname} ({screen_type_name})"
    if font:
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_x = (width_px - text_width) // 2
        text_y = height_px - 30
        draw.text((text_x, text_y), text, fill=0, font=font)
    
    return img


def add_reference_elements(draw: ImageDraw.Draw, width: int, height: int, screen_type):
    """Add reference elements for scale and perspective correction."""
    # Add corner markers for perspective correction
    marker_size = 20
    
    # Top-left corner
    draw.rectangle([5, 5, 5 + marker_size, 5 + marker_size], fill=0)
    draw.rectangle([10, 10, 10 + marker_size//2, 10 + marker_size//2], fill=255)
    
    # Top-right corner  
    draw.rectangle([width - 5 - marker_size, 5, width - 5, 5 + marker_size], fill=0)
    draw.rectangle([width - 10 - marker_size//2, 10, width - 10, 10 + marker_size//2], fill=255)
    
    # Bottom-left corner
    draw.rectangle([5, height - 5 - marker_size, 5 + marker_size, height - 5], fill=0)
    draw.rectangle([10, height - 10 - marker_size//2, 10 + marker_size//2, height - 10], fill=255)
    
    # Bottom-right corner
    draw.rectangle([width - 5 - marker_size, height - 5 - marker_size, width - 5, height - 5], fill=0)
    draw.rectangle([width - 10 - marker_size//2, height - 10 - marker_size//2, width - 10, height - 10], fill=255)
    
    # Add scale reference - a known-size rectangle
    # Use 10mm as reference size
    ref_size_mm = 10.0
    dpi = 150
    ref_size_px = int(ref_size_mm * dpi / 25.4)
    
    # Place reference rectangle in top center
    ref_x = (width - ref_size_px) // 2
    ref_y = 50
    draw.rectangle([ref_x, ref_y, ref_x + ref_size_px, ref_y + ref_size_px], fill=0, outline=0, width=2)
    
    # Add measurement lines for the reference
    line_extend = 10
    draw.line([ref_x - line_extend, ref_y - 5, ref_x + ref_size_px + line_extend, ref_y - 5], fill=0, width=1)
    draw.line([ref_x - line_extend, ref_y + ref_size_px + 5, ref_x + ref_size_px + line_extend, ref_y + ref_size_px + 5], fill=0, width=1)
    draw.line([ref_x - 5, ref_y - line_extend, ref_x - 5, ref_y + ref_size_px + line_extend], fill=0, width=1)
    draw.line([ref_x + ref_size_px + 5, ref_y - line_extend, ref_x + ref_size_px + 5, ref_y + ref_size_px + line_extend], fill=0, width=1)


def detect_qr_positions(pil_image: Image.Image) -> List[QRPositionData]:
    """Detect QR codes and extract positioning information from PIL image."""
    import numpy as np
    
    # Convert PIL to RGB if needed, then to BGR for OpenCV
    if pil_image.mode != 'RGB':
        pil_image = pil_image.convert('RGB')
    image = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
    
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    
    # Detect QR codes
    qr_codes = pyzbar.decode(gray)
    
    position_data = []
    
    for qr in qr_codes:
        try:
            # Decode QR data
            data = qr.data.decode('utf-8')
            if not data.startswith('DIGINK:'):
                continue
                
            parts = data.split(':')
            if len(parts) != 3:
                continue
                
            hostname = parts[1]
            screen_type = parts[2]
            
            # Get QR code position and orientation
            corners = [(point.x, point.y) for point in qr.polygon]
            
            # Calculate center
            center_x = sum(corner[0] for corner in corners) / len(corners)
            center_y = sum(corner[1] for corner in corners) / len(corners)
            
            # Calculate rotation using reference square
            rotation = calculate_qr_rotation(corners, gray)
            
            # Find reference element size for scale calculation
            ref_size = detect_reference_element_size(gray, (center_x, center_y))
            
            position_data.append(QRPositionData(
                hostname=hostname,
                center=(center_x, center_y),
                rotation=rotation,
                corners=corners,
                reference_size=ref_size
            ))
            
        except Exception as e:
            print(f"Error processing QR code: {e}")
            continue
    
    return position_data


def detect_reference_square(gray_image: np.ndarray, qr_center: Tuple[float, float], qr_corners: List[Tuple[float, float]]) -> Optional[Tuple[float, float]]:
    """Detect the black reference square near the QR code."""
    # Search area around QR code (expand by 50% in each direction)
    qr_x_coords = [c[0] for c in qr_corners]
    qr_y_coords = [c[1] for c in qr_corners]
    
    qr_left = min(qr_x_coords)
    qr_right = max(qr_x_coords)
    qr_top = min(qr_y_coords)
    qr_bottom = max(qr_y_coords)
    
    qr_width = qr_right - qr_left
    qr_height = qr_bottom - qr_top
    
    # Search area (expand by 100% to catch reference square)
    search_left = max(0, int(qr_left - qr_width))
    search_right = min(gray_image.shape[1], int(qr_right + qr_width))
    search_top = max(0, int(qr_top - qr_height))
    search_bottom = min(gray_image.shape[0], int(qr_bottom + qr_height))
    
    search_region = gray_image[search_top:search_bottom, search_left:search_right]
    
    # Find contours (black squares)
    _, thresh = cv2.threshold(search_region, 127, 255, cv2.THRESH_BINARY)
    thresh = cv2.bitwise_not(thresh)  # Invert to find black areas
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    # Look for square-like contours
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < 100 or area > 10000:  # Filter by reasonable size
            continue
            
        # Check if contour is roughly square
        approx = cv2.approxPolyDP(contour, 0.02 * cv2.arcLength(contour, True), True)
        if len(approx) >= 4:  # Roughly rectangular
            # Get bounding box
            x, y, w, h = cv2.boundingRect(contour)
            aspect_ratio = float(w) / h
            
            if 0.7 <= aspect_ratio <= 1.3:  # Roughly square
                # Convert back to full image coordinates
                ref_center_x = search_left + x + w // 2
                ref_center_y = search_top + y + h // 2
                
                # Check if it's not the QR code itself (should be smaller and separate)
                distance = math.sqrt((ref_center_x - qr_center[0])**2 + (ref_center_y - qr_center[1])**2)
                if distance > min(qr_width, qr_height) * 0.3:  # At least 30% of QR size away
                    return (ref_center_x, ref_center_y)
    
    return None


def calculate_qr_rotation(corners: List[Tuple[float, float]], gray_image: np.ndarray) -> float:
    """Calculate rotation angle using reference square position."""
    if len(corners) < 4:
        return 0.0
    
    # Find QR center
    center_x = sum(c[0] for c in corners) / len(corners)
    center_y = sum(c[1] for c in corners) / len(corners)
    qr_center = (center_x, center_y)
    
    # Try to find the reference square
    ref_pos = detect_reference_square(gray_image, qr_center, corners)
    
    if ref_pos:
        # Calculate angle from QR center to reference square
        dx = ref_pos[0] - center_x
        dy = ref_pos[1] - center_y
        
        # Angle from QR center to reference square
        ref_angle = math.degrees(math.atan2(dy, dx))
        
        # In original image, reference square is at "top center" (270° or -90°)
        # Calculate rotation by comparing to expected position
        rotation = ref_angle - (-90)  # Adjust for expected "top" position
        
        # Normalize to -180 to 180 range
        rotation = ((rotation + 180) % 360) - 180
        
        # Debug output for 180° vs 0° confusion
        print(f"QR rotation debug: center=({center_x:.1f},{center_y:.1f}), ref=({ref_pos[0]:.1f},{ref_pos[1]:.1f}), ref_angle={ref_angle:.1f}°, rotation={rotation:.1f}°")
        
        return rotation
    else:
        print(f"QR rotation debug: No reference square found near ({center_x:.1f},{center_y:.1f})")
        return 0.0


def detect_reference_element_size(gray_image: np.ndarray, qr_center: Tuple[float, float]) -> float:
    """Detect the reference element size near the QR code."""
    # This is a simplified implementation
    # In practice, you'd use more sophisticated image processing
    # to find the reference rectangle and measure its size
    
    # For now, return a placeholder value
    # This should be implemented based on the specific reference elements used
    return 50.0  # placeholder


def calculate_physical_positions(position_data: List[QRPositionData], config: Config) -> Dict[str, Dict]:
    """Convert image coordinates to physical coordinates with perspective correction."""
    if not position_data:
        return {}
    
    # Calculate scale factor using reference elements
    # Assumes 10mm reference squares
    reference_size_mm = 10.0
    
    results = {}
    
    # Find average scale factor from all detected screens
    scale_factors = []
    for data in position_data:
        if data.reference_size > 0:
            scale_factor = reference_size_mm / data.reference_size
            scale_factors.append(scale_factor)
    
    if not scale_factors:
        print("Warning: No reference elements detected for scale calculation")
        return {}
    
    avg_scale = sum(scale_factors) / len(scale_factors)
    
    # Convert positions to physical coordinates
    # Use the first detected screen as origin (0,0)
    if position_data:
        origin = position_data[0].center
        
        for data in position_data:
            # Calculate relative position from origin
            rel_x = (data.center[0] - origin[0]) * avg_scale
            rel_y = (data.center[1] - origin[1]) * avg_scale
            
            results[data.hostname] = {
                'x': int(rel_x),
                'y': int(rel_y),
                'rotation': data.rotation,
                'scale_factor': avg_scale
            }
    
    return results


def generate_updated_config(original_config: Config, positions: Dict[str, Dict]) -> Dict:
    """Generate updated device configuration with detected positions."""
    # Create new devices list with updated coordinates
    devices_yaml = []
    
    for device in original_config.devices:
        if device.host in positions:
            pos = positions[device.host]
            
            # Try to get actual screen type from device
            try:
                from .device import info
                device_info = info(device.host)
                actual_screen_type = device_info.screen_model
            except:
                # Fall back to configured screen type
                actual_screen_type = device.screen_type.__class__.__name__.replace('ScreenType', '')
            
            device_yaml = {
                'host': device.host,
                'screen_type': actual_screen_type,
                'coordinates': {
                    'x': pos['x'],
                    'y': pos['y']
                }
            }
            # Add rotation if significant (not close to 0)
            if abs(pos['rotation']) > 5:  # More than 5 degrees
                device_yaml['rotation'] = int(pos['rotation'])
        else:
            # Keep original coordinates if not detected
            try:
                from .device import info
                device_info = info(device.host)
                actual_screen_type = device_info.screen_model
            except:
                actual_screen_type = device.screen_type.__class__.__name__.replace('ScreenType', '')
            
            device_yaml = {
                'host': device.host,
                'screen_type': actual_screen_type,
                'coordinates': {
                    'x': device.coordinates.x,
                    'y': device.coordinates.y
                }
            }
        
        devices_yaml.append(device_yaml)
    
    return {'devices': devices_yaml}