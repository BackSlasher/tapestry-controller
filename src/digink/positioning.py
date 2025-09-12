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
import subprocess
import requests
import json
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
    screen_corners: Optional[List[Tuple[float, float]]]  # Detected screen corner positions


class ReferenceElement(NamedTuple):
    """Reference element for scale and perspective correction."""
    actual_size_mm: float  # known physical size in mm
    pixel_size: float  # measured size in pixels from photo


class DiscoveredDevice(NamedTuple):
    """Device discovered from DHCP leases."""
    ip: str
    screen_type: str


def discover_devices_from_dhcp() -> List[DiscoveredDevice]:
    """Discover devices from DHCP leases and query their screen types."""
    devices = []
    
    try:
        # Read DHCP leases file
        result = subprocess.run(
            ['sudo', 'cat', '/var/lib/NetworkManager/dnsmasq-wlan0.leases'],
            capture_output=True, text=True, check=True
        )
        
        for line in result.stdout.strip().split('\n'):
            if not line.strip():
                continue
                
            parts = line.split()
            if len(parts) >= 3:
                ip = parts[2]
                
                # Query device for screen type
                screen_type = get_device_screen_type(ip)
                if screen_type:
                    devices.append(DiscoveredDevice(ip, screen_type))
                    print(f"Discovered device: {ip} - {screen_type}")
    
    except subprocess.CalledProcessError as e:
        print(f"Error reading DHCP leases: {e}")
    except Exception as e:
        print(f"Error discovering devices: {e}")
    
    return devices


def get_device_screen_type(ip: str, timeout: int = 5) -> Optional[str]:
    """Query device HTTP endpoint to get screen type."""
    try:
        response = requests.get(f'http://{ip}/', timeout=timeout)
        if response.status_code == 200:
            data = response.json()
            return data.get('screen_model', 'Unknown')
    except requests.exceptions.RequestException:
        # Device might not be responding or not a digink device
        pass
    except json.JSONDecodeError:
        # Response is not JSON
        pass
    except Exception as e:
        print(f"Error querying device {ip}: {e}")
    
    return None


def generate_all_positioning_qr_images() -> Dict[str, Image.Image]:
    """Generate QR positioning images for all discovered devices."""
    qr_images = {}
    
    print("Discovering devices from DHCP leases...")
    devices = discover_devices_from_dhcp()
    
    if not devices:
        print("No devices discovered from DHCP leases")
        return qr_images
    
    print(f"Found {len(devices)} devices, generating QR codes...")
    
    for device in devices:
        try:
            qr_img = generate_positioning_qr_image(device.ip, device.screen_type)
            qr_images[device.ip] = qr_img
            print(f"Generated QR for {device.ip} ({device.screen_type})")
        except KeyError as e:
            print(f"Unknown screen type '{device.screen_type}' for device {device.ip}: {e}")
        except Exception as e:
            print(f"Error generating QR for {device.ip}: {e}")
    
    return qr_images


def generate_positioning_qr_image(ip: str, screen_type_name: str) -> Image.Image:
    """Generate full-screen QR code with corner markers for precise positioning."""
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
    qr_data = f"DIGINK:{ip}:{screen_type_name}"
    
    # Calculate QR size to fill most of the screen (leave margin for corners)
    margin = 60  # pixels for corner markers
    available_width = width_px - (2 * margin)
    available_height = height_px - (2 * margin)
    
    # Make QR size fit the smaller dimension to keep it square
    qr_size = min(available_width, available_height)
    
    # Calculate box_size to achieve desired QR pixel size
    # QR version 3 is 29x29 modules, version 4 is 33x33, etc.
    # Start with a reasonable version and calculate box size
    qr = qrcode.QRCode(
        version=1,  # Start small and let it grow
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=1,  # We'll calculate this
        border=1,   # Minimal border since we control the positioning
    )
    qr.add_data(qr_data)
    qr.make(fit=True)
    
    # Calculate box size to achieve target QR size
    modules_count = qr.modules_count  # Total modules in QR (including border)
    box_size = max(1, qr_size // modules_count)
    
    # Recreate QR with calculated box size
    qr = qrcode.QRCode(
        version=qr.version,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=box_size,
        border=1,
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
    
    # Add corner markers and lines
    add_screen_boundary_markers(draw, width_px, height_px, qr_x + qr_width//2, qr_y + qr_height//2)
    
    # Add screen info text at bottom
    try:
        font = ImageFont.load_default()
    except:
        font = None
    
    text = f"{ip} - {screen_type_name} - {screen_type.active_area.width:.0f}x{screen_type.active_area.height:.0f}mm"
    if font:
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_x = (width_px - text_width) // 2
        text_y = height_px - 25
        
        # White background for text readability
        draw.rectangle([text_x-5, text_y-3, text_x+text_width+5, text_y+15], fill=255)
        draw.text((text_x, text_y), text, fill=0, font=font)
    
    return img


def add_screen_boundary_markers(draw: ImageDraw.Draw, width: int, height: int, qr_center_x: int, qr_center_y: int):
    """Add corner markers and lines to clearly define screen boundaries."""
    
    # Large, distinctive corner markers
    marker_size = 40  # Bigger than before
    marker_thickness = 8
    
    # Corner positions (inset from edges for visibility)
    inset = 15
    corners = [
        (inset, inset),  # Top-left
        (width - inset - marker_size, inset),  # Top-right  
        (inset, height - inset - marker_size),  # Bottom-left
        (width - inset - marker_size, height - inset - marker_size),  # Bottom-right
    ]
    
    # Draw corner markers - distinctive "L" shapes
    for i, (x, y) in enumerate(corners):
        # Thick black "L" shape
        # Horizontal line
        draw.rectangle([x, y, x + marker_size, y + marker_thickness], fill=0)
        # Vertical line  
        draw.rectangle([x, y, x + marker_thickness, y + marker_size], fill=0)
        
        # White inner area for contrast
        draw.rectangle([x + marker_thickness, y + marker_thickness, 
                       x + marker_size//2, y + marker_size//2], fill=255)
    
    # Draw lines from QR center to each corner for clear association
    line_thickness = 3
    for corner_x, corner_y in corners:
        # Calculate line endpoint (to corner center)
        end_x = corner_x + marker_size // 2
        end_y = corner_y + marker_size // 2
        
        # Draw line from QR center to corner
        draw.line([qr_center_x, qr_center_y, end_x, end_y], fill=128, width=line_thickness)
    
    # Add screen boundary rectangle for extra clarity
    border_thickness = 5
    draw.rectangle([5, 5, width-5, height-5], outline=0, width=border_thickness)


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
                
            ip = parts[1]  # Now using IP instead of hostname
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
            
            # Detect screen corners using corner markers
            screen_corners = detect_screen_corners(gray, (center_x, center_y), corners)
            
            position_data.append(QRPositionData(
                hostname=ip,  # Now storing IP in hostname field
                screen_type=screen_type,
                center=(center_x, center_y),
                rotation=rotation,
                corners=corners,
                reference_size=ref_size,
                screen_corners=screen_corners
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


def detect_screen_corners(gray_image: np.ndarray, qr_center: Tuple[float, float], qr_corners: List[Tuple[float, float]]) -> Optional[List[Tuple[float, float]]]:
    """Detect the L-shaped corner markers to find actual screen boundaries."""
    
    # Estimate search area around QR code - should cover most of the screen
    qr_x_coords = [c[0] for c in qr_corners]
    qr_y_coords = [c[1] for c in qr_corners]
    
    qr_left = min(qr_x_coords)
    qr_right = max(qr_x_coords)
    qr_top = min(qr_y_coords)
    qr_bottom = max(qr_y_coords)
    
    qr_width = qr_right - qr_left
    qr_height = qr_bottom - qr_top
    
    # Expand search area to cover entire screen (QR is ~75% of screen)
    expansion_factor = 1.5
    search_left = max(0, int(qr_left - qr_width * expansion_factor * 0.5))
    search_right = min(gray_image.shape[1], int(qr_right + qr_width * expansion_factor * 0.5))
    search_top = max(0, int(qr_top - qr_height * expansion_factor * 0.5))
    search_bottom = min(gray_image.shape[0], int(qr_bottom + qr_height * expansion_factor * 0.5))
    
    search_region = gray_image[search_top:search_bottom, search_left:search_right]
    
    # Find L-shaped corner markers using contour detection
    _, thresh = cv2.threshold(search_region, 127, 255, cv2.THRESH_BINARY)
    thresh = cv2.bitwise_not(thresh)  # Invert to find black areas
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    corner_candidates = []
    
    # Look for L-shaped contours
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < 200 or area > 10000:  # Filter by reasonable size
            continue
            
        # Get bounding box
        x, y, w, h = cv2.boundingRect(contour)
        aspect_ratio = float(w) / h
        
        # L-shapes should be roughly square overall
        if 0.5 <= aspect_ratio <= 2.0:
            # Convert back to full image coordinates
            corner_x = search_left + x + w // 2
            corner_y = search_top + y + h // 2
            corner_candidates.append((corner_x, corner_y))
    
    # Sort by distance from QR center and take the 4 closest (should be the 4 corners)
    qr_cx, qr_cy = qr_center
    corner_candidates.sort(key=lambda c: (c[0] - qr_cx)**2 + (c[1] - qr_cy)**2)
    
    if len(corner_candidates) >= 4:
        # Take the 4 closest corner markers
        screen_corners = corner_candidates[:4]
        
        # Sort corners in clockwise order: top-left, top-right, bottom-right, bottom-left
        # First, separate by Y coordinate to get top/bottom
        screen_corners.sort(key=lambda c: c[1])  # Sort by Y
        top_corners = screen_corners[:2]
        bottom_corners = screen_corners[2:4]
        
        # Sort top corners by X (left to right)
        top_corners.sort(key=lambda c: c[0])
        # Sort bottom corners by X (left to right) 
        bottom_corners.sort(key=lambda c: c[0])
        
        # Return in order: top-left, top-right, bottom-right, bottom-left
        ordered_corners = [
            top_corners[0],     # top-left
            top_corners[1],     # top-right
            bottom_corners[1],  # bottom-right
            bottom_corners[0]   # bottom-left
        ]
        
        return ordered_corners
    
    return None


def detect_reference_element_size(gray_image: np.ndarray, qr_center: Tuple[float, float]) -> float:
    """Detect the reference element size near the QR code."""
    # This is a simplified implementation
    # In practice, you'd use more sophisticated image processing
    # to find the reference rectangle and measure its size
    
    # For now, return a placeholder value
    # This should be implemented based on the specific reference elements used
    return 50.0  # placeholder


def calculate_physical_positions(position_data: List[QRPositionData], config: Config) -> Dict[str, Dict]:
    """Convert image coordinates to physical coordinates using QR-based screen boundary calculation."""
    if not position_data:
        return {}
    
    print(f"\n=== QR-Based Screen Boundary Calculation for {len(position_data)} screens ===")
    
    # Step 1: Calculate scale using QR dimensions  
    total_scale = 0
    scale_count = 0
    screen_positions = []
    
    for data in position_data:
        if data.screen_type in SCREEN_TYPES and len(data.corners) >= 4:
            screen_type = SCREEN_TYPES[data.screen_type]
            
            # Calculate QR dimensions in pixels
            x_coords = [c[0] for c in data.corners]
            y_coords = [c[1] for c in data.corners]
            qr_width_px = max(x_coords) - min(x_coords)
            qr_height_px = max(y_coords) - min(y_coords)
            
            # QR fills ~75% of screen, so calculate actual screen dimensions in pixels
            screen_width_px = qr_width_px / 0.75
            screen_height_px = qr_height_px / 0.75
            
            # Get actual physical screen dimensions
            actual_width_mm = screen_type.active_area.width
            actual_height_mm = screen_type.active_area.height
            
            # Calculate scale factor (mm per pixel)
            scale_x = actual_width_mm / screen_width_px
            scale_y = actual_height_mm / screen_height_px
            scale_factor = (scale_x + scale_y) / 2
            
            total_scale += scale_factor
            scale_count += 1
            
            # Calculate screen top-left corner from QR center
            # QR is centered on screen, so screen top-left is at:
            qr_cx, qr_cy = data.center
            screen_top_left_x = qr_cx - (screen_width_px / 2)
            screen_top_left_y = qr_cy - (screen_height_px / 2)
            
            # Convert to mm coordinates
            screen_top_left_x_mm = screen_top_left_x * scale_factor
            screen_top_left_y_mm = screen_top_left_y * scale_factor
            
            screen_positions.append({
                'hostname': data.hostname,
                'screen_type': data.screen_type,
                'top_left_x': screen_top_left_x_mm,
                'top_left_y': screen_top_left_y_mm,
                'rotation': data.rotation,
                'qr_center': data.center,
                'screen_width_px': screen_width_px,
                'screen_height_px': screen_height_px,
                'scale_factor': scale_factor
            })
            
            print(f"Screen {data.hostname} ({data.screen_type}):")
            print(f"  QR: {qr_width_px:.0f}x{qr_height_px:.0f}px at ({qr_cx:.0f},{qr_cy:.0f})")
            print(f"  Screen: {screen_width_px:.0f}x{screen_height_px:.0f}px → {actual_width_mm}x{actual_height_mm}mm")
            print(f"  Top-left: ({screen_top_left_x:.0f},{screen_top_left_y:.0f})px → ({screen_top_left_x_mm:.0f},{screen_top_left_y_mm:.0f})mm")
            print(f"  Scale: {scale_factor:.4f} mm/px")
    
    if scale_count == 0:
        print("ERROR: Could not calculate scale from any screens!")
        return {}
    
    avg_scale = total_scale / scale_count
    print(f"Average scale: {avg_scale:.4f} mm/pixel")
    
    # Step 2: Find bounds and normalize coordinates  
    if not screen_positions:
        return {}
    
    min_x = min(pos['top_left_x'] for pos in screen_positions)
    min_y = min(pos['top_left_y'] for pos in screen_positions)
    
    print(f"Screen bounds: X=[{min_x:.0f}, {max(pos['top_left_x'] for pos in screen_positions):.0f}], Y=[{min_y:.0f}, {max(pos['top_left_y'] for pos in screen_positions):.0f}]")
    
    # Step 3: Create final coordinates based on TOP-LEFT positions
    margin = 20  # Small margin for clean layout
    results = {}
    
    for pos in screen_positions:
        # Normalize so leftmost screen starts at margin, topmost at margin
        final_x = int(pos['top_left_x'] - min_x + margin)
        final_y = int(pos['top_left_y'] - min_y + margin)
        
        results[pos['hostname']] = {
            'x': final_x,
            'y': final_y,
            'rotation': pos['rotation'],
            'scale_factor': avg_scale,
            'screen_type': pos['screen_type']
        }
        
        print(f"  FINAL {pos['hostname']}: ({final_x}, {final_y}) - screen boundary positioned")
    
    return results


def generate_updated_config(original_config: Config, positions: Dict[str, Dict]) -> Dict:
    """Generate updated device configuration with detected positions."""
    # Create new devices list with detected coordinates
    devices_yaml = []
    
    # First, add all detected devices (these are the primary ones from QR detection)
    for ip_or_host, pos in positions.items():
        # Try to get actual screen type from device
        try:
            screen_type = get_device_screen_type(ip_or_host)
            if not screen_type:
                print(f"Warning: Could not determine screen type for {ip_or_host}")
                continue
        except:
            print(f"Warning: Could not query screen type for {ip_or_host}")
            continue
        
        device_yaml = {
            'host': ip_or_host,  # Use IP address as host
            'screen_type': screen_type,
            'coordinates': {
                'x': pos['x'],
                'y': pos['y']
            }
        }
        
        # Add rotation if significant (not close to 0)
        if abs(pos['rotation']) > 5:  # More than 5 degrees
            device_yaml['rotation'] = int(pos['rotation'])
        
        devices_yaml.append(device_yaml)
    
    # Add any existing devices that weren't detected (to preserve them)
    for device in original_config.devices:
        # Check if this device was already added from detected positions
        device_found = any(d['host'] == device.host for d in devices_yaml)
        
        if not device_found:
            # Keep original device configuration
            try:
                screen_type = get_device_screen_type(device.host)
                if not screen_type:
                    screen_type = device.screen_type.__class__.__name__.replace('ScreenType', '')
            except:
                screen_type = device.screen_type.__class__.__name__.replace('ScreenType', '')
            
            device_yaml = {
                'host': device.host,
                'screen_type': screen_type,
                'coordinates': {
                    'x': device.coordinates.x,
                    'y': device.coordinates.y
                }
            }
            
            if device.rotation != 0:
                device_yaml['rotation'] = device.rotation
            
            devices_yaml.append(device_yaml)
    
    return {'devices': devices_yaml}