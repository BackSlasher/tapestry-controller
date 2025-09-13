"""
QR code generation and device discovery for positioning system.
"""

import io
import qrcode
import subprocess
import requests
from PIL import Image, ImageDraw
from typing import Dict, List, Tuple, NamedTuple, Optional
from .screen_types import SCREEN_TYPES


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
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            print(f"Failed to read DHCP leases: {result.stderr}")
            return devices
        
        # Parse leases
        for line in result.stdout.strip().split('\n'):
            if not line.strip():
                continue
            
            parts = line.split()
            if len(parts) >= 3:
                ip = parts[2]
                
                # Query device for screen type
                screen_type = get_device_screen_type(ip)
                if screen_type:
                    devices.append(DiscoveredDevice(ip=ip, screen_type=screen_type))
                    print(f"Discovered device: {ip} ({screen_type})")
                else:
                    print(f"Could not determine screen type for {ip}")
    
    except subprocess.TimeoutExpired:
        print("Timeout reading DHCP leases")
    except Exception as e:
        print(f"Error discovering devices from DHCP: {e}")
    
    return devices


def get_device_screen_type(ip: str, timeout: int = 5) -> Optional[str]:
    """Query a device's screen type via HTTP."""
    try:
        response = requests.get(f"http://{ip}/screen-type", timeout=timeout)
        if response.status_code == 200:
            return response.text.strip()
    except Exception as e:
        print(f"Failed to get screen type from {ip}: {e}")
    
    return None


def generate_positioning_qr_image(ip: str, screen_type_name: str) -> Image.Image:
    """Generate QR positioning image for a specific device."""
    
    # Get screen type info
    if screen_type_name not in SCREEN_TYPES:
        raise ValueError(f"Unknown screen type: {screen_type_name}")
    
    screen_type = SCREEN_TYPES[screen_type_name]
    
    # Calculate image size based on screen dimensions
    # Use screen's active area for sizing
    width_mm = screen_type.active_area.width
    height_mm = screen_type.active_area.height
    
    # Use 4 pixels per mm for good resolution
    pixels_per_mm = 4
    width = int(width_mm * pixels_per_mm)
    height = int(height_mm * pixels_per_mm)
    
    # Create white background
    img = Image.new('1', (width, height), 1)  # '1' mode for 1-bit black/white
    draw = ImageDraw.Draw(img)
    
    # QR code data format: DIGINK:IP:SCREEN_TYPE
    qr_data = f"DIGINK:{ip}:{screen_type_name}"
    
    # Generate QR code - make it large and centered
    qr = qrcode.QRCode(
        version=1,  # Controls the size
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=6,  # Size of each box
        border=4,    # Border size
    )
    qr.add_data(qr_data)
    qr.make(fit=True)
    
    # Create QR image
    qr_img = qr.make_image(fill_color="black", back_color="white")
    
    # Calculate position to center QR code
    qr_width, qr_height = qr_img.size
    
    # Scale QR to take up about 75% of the screen
    target_size = min(width, height) * 0.75
    scale_factor = target_size / max(qr_width, qr_height)
    
    new_width = int(qr_width * scale_factor)
    new_height = int(qr_height * scale_factor)
    qr_img = qr_img.resize((new_width, new_height), Image.LANCZOS)
    
    # Center the QR code
    qr_x = (width - new_width) // 2
    qr_y = (height - new_height) // 2
    
    # Convert to same mode and paste
    qr_img_bw = qr_img.convert('1')
    img.paste(qr_img_bw, (qr_x, qr_y))
    
    return img


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
            print(f"Generated QR code for {device.ip} ({device.screen_type})")
        except Exception as e:
            print(f"Failed to generate QR code for {device.ip}: {e}")
    
    return qr_images