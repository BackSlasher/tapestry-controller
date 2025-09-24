"""
QR code generation and device discovery for positioning system.
"""

import io
import json
import qrcode
import subprocess
import requests
from PIL import Image, ImageDraw
from typing import Dict, List, Tuple, NamedTuple, Optional
from .screen_types import SCREEN_TYPES


class DiscoveredDevice(NamedTuple):
    """Device discovered from DHCP leases."""

    ip: str
    hostname: str
    screen_type: str


def discover_devices_from_dhcp() -> List[DiscoveredDevice]:
    """Discover devices from DHCP leases and query their screen types."""
    devices = []

    try:
        # Read DHCP leases file
        result = subprocess.run(
            ["sudo", "cat", "/var/lib/NetworkManager/dnsmasq-wlan0.leases"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            print(f"Failed to read DHCP leases: {result.stderr}")
            return devices

        # Parse leases
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue

            parts = line.split()
            if len(parts) >= 4:
                ip = parts[2]
                hostname = parts[3] if len(parts) > 3 and parts[3] != "*" else ip

                # Query device for screen type
                screen_type = get_device_screen_type(ip)
                if screen_type:
                    devices.append(
                        DiscoveredDevice(
                            ip=ip, hostname=hostname, screen_type=screen_type
                        )
                    )
                    print(f"Discovered device: {hostname} ({ip}) - {screen_type}")
                else:
                    print(f"Could not determine screen type for {hostname} ({ip})")

    except subprocess.TimeoutExpired:
        print("Timeout reading DHCP leases")
    except Exception as e:
        print(f"Error discovering devices from DHCP: {e}")

    return devices


def get_device_screen_type(ip: str, timeout: int = 5) -> Optional[str]:
    """Query a device's screen type via HTTP."""
    try:
        response = requests.get(f"http://{ip}/", timeout=timeout)
        if response.status_code == 200:
            data = response.json()
            return data.get("screen_model")
    except Exception as e:
        print(f"Failed to get screen type from {ip}: {e}")

    return None


def generate_positioning_qr_image(
    ip: str, hostname: str, screen_type_name: str
) -> Image.Image:
    """Generate QR positioning image for a specific device."""

    # Get screen type info
    if screen_type_name not in SCREEN_TYPES:
        raise ValueError(f"Unknown screen type: {screen_type_name}")

    # Get actual pixel dimensions from device
    response = requests.get(f"http://{ip}/", timeout=5)
    response.raise_for_status()
    device_data = response.json()
    width = int(device_data["width"])
    height = int(device_data["height"])

    # Pre-calculate QR code size (75% of screen size)
    target_size = min(width, height) * 0.75

    # Create JSON data to encode in QR
    qr_json_data = {
        "host": hostname,  # hostname only (no IP needed)
        "screen_type": screen_type_name,
        "screen_width_px": width,
        "screen_height_px": height,
        "qr_size_px": int(target_size),
    }
    qr_data = f"DIGINK:{json.dumps(qr_json_data)}"

    # Generate QR code with medium error correction
    qr = qrcode.QRCode(
        version=None,  # Auto-size based on data
        error_correction=qrcode.constants.ERROR_CORRECT_M,  # Medium error correction (15%)
        box_size=1,  # Will be scaled later
        border=4,  # Standard quiet zone
    )
    qr.add_data(qr_data)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white")

    qr_width, qr_height = qr_img.size

    min_module_size = 3  # pixels per module
    modules_per_side = qr.modules_count
    min_qr_size = modules_per_side * min_module_size
    if target_size < min_qr_size:
        raise Exception(f"QR code too small for {ip}")

    scale_factor = target_size / max(qr_width, qr_height)
    new_width = int(qr_width * scale_factor)
    new_height = int(qr_height * scale_factor)
    qr_img = qr_img.resize((new_width, new_height), Image.LANCZOS)

    # Create white background
    img = Image.new("1", (width, height), 1)  # '1' mode for 1-bit black/white

    # Center the QR code
    qr_x = (width - new_width) // 2
    qr_y = (height - new_height) // 2

    # Convert to same mode and paste
    qr_img_bw = qr_img.convert("1")
    img.paste(qr_img_bw, (qr_x, qr_y))

    print(
        f"Generated QR code for {ip}: {new_width}x{new_height}px at ({qr_x},{qr_y}), data: {qr_json_data}"
    )

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
        qr_img = generate_positioning_qr_image(
            device.ip, device.hostname, device.screen_type
        )
        qr_images[device.ip] = qr_img
        print(
            f"Generated QR code for {device.hostname} ({device.ip}) - {device.screen_type}"
        )

    return qr_images
