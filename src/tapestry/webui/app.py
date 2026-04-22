#!/usr/bin/env python3
import argparse
import glob
import hashlib
import io
import logging
import os
import queue
import threading

import PIL.Image
from flask import (
    Flask,
    Response,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from PIL import ImageDraw, ImageFont

from ..controller import TapestryController
from ..curation import CurationManager
from ..geometry import Dimensions, Point, Rectangle
from ..screen_types import SCREEN_TYPES
from ..settings import (
    GallerySettings,
    PixabaySettings,
    RedditSettings,
    ScreensaverSettings,
    get_settings,
)
from .device_monitor import DeviceMonitor, MonitorConfig
from .flash_manager import FlashManager
from .image_cache import ImageCache
from .ota_manager import OTAManager
from .process_manager import ProcessManager
from .screensaver import ScreensaverManager
from .screensaver_v2 import ScreensaverV2

app = Flask(__name__)
# Secure secret key from settings with auto-generation
app.config["SECRET_KEY"] = get_settings().ensure_secure_webui_config()
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB max file size

# Set up logging
logger = logging.getLogger(__name__)

# Global controller instance
controller: TapestryController | None = None
image_cache = ImageCache()


def get_controller() -> TapestryController:
    if controller is None:
        raise Exception("No controller")
    return controller


def reload_device_config(devices_file: str = "devices.yaml"):
    """Reload device configuration and update both controller and device monitor."""
    global controller, device_monitor

    # Reload controller configuration
    from ..models import load_config

    new_config = load_config(devices_file)
    get_controller().config = new_config

    # Update device monitor with new device list
    if device_monitor:
        device_hosts = [device.host for device in new_config.devices]
        device_monitor.update_device_list(device_hosts)
        logger.info(f"Updated device monitor with {len(device_hosts)} devices")

    logger.info(f"Reloaded configuration from {devices_file}")


# Screensaver manager instance (legacy)
screensaver_manager: ScreensaverManager | None = None

# New curation-based screensaver
curation_manager: CurationManager | None = None
screensaver_v2: ScreensaverV2 | None = None

# OTA manager instance
ota_manager: OTAManager | None = None

# Device monitor instance
device_monitor: DeviceMonitor | None = None

# Flash manager instance
flash_manager: FlashManager | None = None

# Process manager instance (shared between flash and OTA)
process_manager: ProcessManager | None = None


def get_layout_aspect_ratio() -> float | None:
    """Calculate the target aspect ratio from device layout.

    Returns:
        Aspect ratio (width/height) of the bounding rectangle, or None if no devices.
    """
    if not controller or not controller.config.devices:
        return None

    from .collections_manager import get_collection_path

    device_rectangles = {}
    for device in controller.config.devices:
        start = Point(x=device.coordinates.x, y=device.coordinates.y)
        dimensions = Dimensions(
            width=device.detected_dimensions.width,
            height=device.detected_dimensions.height,
        )
        device_rectangles[device] = Rectangle(start=start, dimensions=dimensions)

    bounding = Rectangle.bounding_rectangle(list(device_rectangles.values()))
    return bounding.dimensions.width / bounding.dimensions.height


def get_screensaver_config():
    """Get screensaver configuration from settings."""
    settings = get_settings()
    return {
        "enabled": settings.screensaver.enabled,
        "type": settings.screensaver.type,
        "interval": settings.screensaver.interval,
        "gallery": {
            "wallpapers_dir": settings.screensaver.gallery.wallpapers_dir,
            "collections_dir": settings.screensaver.gallery.collections_dir,
            "selected_collection": settings.screensaver.gallery.selected_collection,
        },
        "reddit": {
            "subreddit": settings.screensaver.reddit.subreddit,
            "time_period": settings.screensaver.reddit.time_period,
            "sort": settings.screensaver.reddit.sort,
            "limit": settings.screensaver.reddit.limit,
        },
        "pixabay": {
            "api_key": settings.screensaver.pixabay.api_key,
            "keywords": settings.screensaver.pixabay.keywords,
            "per_page": settings.screensaver.pixabay.per_page,
        },
    }


# Last image state
last_image_state = {
    "image": None,  # PIL Image object
    "refit_image": None,  # Processed/resized image
    "px_in_unit": None,  # Scaling factor
    "thumbnail_cache": None,  # Cached thumbnail for web display
    "thumbnail_max_size": (800, 600),  # Max thumbnail dimensions
}

# Configuration for layout rendering method
USE_SERVER_SIDE_RENDERING = False  # Set to False to use canvas-based rendering


def create_layout_visualization(scaled_image, device_rectangles, mm_to_px_ratio):
    """Create a layout visualization using the new simplified controller logic."""

    # Calculate bounding rectangle in mm (same as controller)
    bounding_rect_mm = Rectangle.bounding_rectangle(list(device_rectangles.values()))

    # Start with the scaled image as the background
    layout_canvas = scaled_image.copy()
    draw = ImageDraw.Draw(layout_canvas)

    # For each device, show where it will be cropped from
    for device, rect_mm in device_rectangles.items():
        # Convert device position from mm to pixels (same as controller)
        device_rect_px = Rectangle(
            start=Point(
                x=int((rect_mm.start.x - bounding_rect_mm.start.x) * mm_to_px_ratio),
                y=int((rect_mm.start.y - bounding_rect_mm.start.y) * mm_to_px_ratio),
            ),
            dimensions=Dimensions(
                width=int(rect_mm.dimensions.width * mm_to_px_ratio),
                height=int(rect_mm.dimensions.height * mm_to_px_ratio),
            ),
        )

        # Draw screen border at the exact position where cropping will occur
        x = device_rect_px.start.x
        y = device_rect_px.start.y
        width = device_rect_px.dimensions.width
        height = device_rect_px.dimensions.height

        # Draw red border to show the crop area
        draw.rectangle([x, y, x + width, y + height], outline="red", width=3)

        # Draw screen label
        try:
            font = ImageFont.load_default()
            label = device.host
            text_bbox = draw.textbbox((0, 0), label, font=font)
            text_width = text_bbox[2] - text_bbox[0]
            text_height = text_bbox[3] - text_bbox[1]

            # White background for text
            text_bg_x = x + 2
            text_bg_y = y + 2
            draw.rectangle(
                [
                    text_bg_x,
                    text_bg_y,
                    text_bg_x + text_width + 4,
                    text_bg_y + text_height + 4,
                ],
                fill=(255, 255, 255, 180),
            )
            draw.text((text_bg_x + 2, text_bg_y + 2), label, fill="black", font=font)
        except Exception as e:
            logger.error(f"Error drawing label for {device.host}: {e}")

    return layout_canvas


def allowed_file(filename):
    """Check if uploaded file has allowed extension."""
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "bmp", "tiff"}
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def get_or_create_thumbnail():
    """Get cached thumbnail or create one from refit_image."""
    if last_image_state["thumbnail_cache"] is not None:
        return last_image_state["thumbnail_cache"]

    if last_image_state["refit_image"] is None:
        return None

    # Create thumbnail
    img = last_image_state["refit_image"].copy()
    img.thumbnail(last_image_state["thumbnail_max_size"], PIL.Image.Resampling.LANCZOS)

    # Cache it
    last_image_state["thumbnail_cache"] = img
    return img


def fix_image_orientation(image):
    """Fix image orientation based on EXIF data and return corrected PIL Image."""
    try:
        # Get EXIF data
        exif = image._getexif()

        if exif is not None:
            # Look for orientation tag (274 is the EXIF orientation tag)
            orientation = exif.get(274, 1)  # 274 is ExifTags.ORIENTATION

            # Apply rotation based on EXIF orientation
            if orientation == 2:
                # Horizontal flip
                image = image.transpose(PIL.Image.Transpose.FLIP_LEFT_RIGHT)
            elif orientation == 3:
                # 180 degree rotation
                image = image.rotate(180, expand=True)
            elif orientation == 4:
                # Vertical flip
                image = image.transpose(PIL.Image.Transpose.FLIP_TOP_BOTTOM)
            elif orientation == 5:
                # Horizontal flip + 90 degree rotation
                image = image.transpose(PIL.Image.Transpose.FLIP_LEFT_RIGHT)
                image = image.rotate(-90, expand=True)
            elif orientation == 6:
                # 90 degree rotation
                image = image.rotate(-90, expand=True)
            elif orientation == 7:
                # Horizontal flip + 270 degree rotation
                image = image.transpose(PIL.Image.Transpose.FLIP_LEFT_RIGHT)
                image = image.rotate(90, expand=True)
            elif orientation == 8:
                # 270 degree rotation
                image = image.rotate(90, expand=True)

    except Exception as e:
        logger.warning(f"Could not fix image orientation: {e}")
        # Return original image if EXIF processing fails

    return image


def load_persisted_image():
    """Load the last image from disk if it exists."""
    try:
        import os

        persist_dir = ".tapestry-data"
        persist_path = os.path.join(persist_dir, "last_image.png")

        if os.path.exists(persist_path):
            image = PIL.Image.open(persist_path)
            save_last_image(image)  # This will recalculate layout and save to memory
            logger.info(f"Restored last image from {persist_path}")
            return True
    except Exception as e:
        logger.warning(f"Could not load persisted image: {e}")

    return False


def save_last_image(image):
    """Save the last sent image for layout overlay."""
    from ..geometry import Dimensions, Point, Rectangle

    # Calculate device rectangles and bounding rectangle (same as controller does)
    device_rectangles = {}
    for device in get_controller().config.devices:
        start = Point(x=device.coordinates.x, y=device.coordinates.y)
        # Use detected dimensions from YAML
        dimensions = Dimensions(
            width=device.detected_dimensions.width,
            height=device.detected_dimensions.height,
        )
        device_rectangles[device] = Rectangle(
            start=start,
            dimensions=dimensions,
        )

    # Process image using the new controller approach
    bounding_rectangle = Rectangle.bounding_rectangle(list(device_rectangles.values()))
    scaled_image, mm_to_px_ratio = get_controller()._scale_image_to_layout(
        image, bounding_rectangle.dimensions
    )

    # Save to global state
    last_image_state["image"] = image.copy()
    last_image_state["refit_image"] = scaled_image.copy()  # Now using scaled_image
    last_image_state["px_in_unit"] = mm_to_px_ratio  # Now using mm_to_px_ratio
    last_image_state["thumbnail_cache"] = None  # Clear thumbnail cache

    # Persist to disk for restart recovery
    try:
        import os

        persist_dir = ".tapestry-data"
        os.makedirs(persist_dir, exist_ok=True)
        persist_path = os.path.join(persist_dir, "last_image.png")
        image.save(persist_path, "PNG")
    except Exception as e:
        logger.warning(f"Could not persist image: {e}")


@app.route("/")
def index():
    """Main page showing layout and upload form."""
    device_count = len(controller.config.devices) if controller else 0
    return render_template("index.html", device_count=device_count)


@app.route("/flash")
def flash_firmware():
    """Flash firmware page."""
    return render_template("flash.html", screen_types=SCREEN_TYPES)


@app.route("/positioning")
def positioning():
    """QR-based positioning page."""
    return render_template("positioning.html")


@app.route("/device-monitoring")
def device_monitoring():
    """Device monitoring page."""
    return render_template("device_monitoring.html")


@app.route("/positioning/qr-mode", methods=["POST"])
def start_qr_positioning():
    """Start QR positioning mode - display QR codes on all discovered devices."""
    try:
        from ..device import draw_unrotated
        from ..qr_generation import generate_all_positioning_qr_images

        # Discover devices from DHCP and generate QR codes
        qr_images = generate_all_positioning_qr_images()

        if not qr_images:
            return (
                jsonify(
                    {
                        "error": "No devices discovered from DHCP leases. Ensure devices are connected and DHCP server is running."
                    }
                ),
                400,
            )

        threads = []
        errors = []

        # Send QR codes to discovered devices
        for ip, qr_image in qr_images.items():
            try:
                t = threading.Thread(target=draw_unrotated, args=(ip, qr_image, True))
                t.daemon = True
                t.start()
                threads.append(t)
            except Exception as e:
                errors.append(f"Error sending QR to {ip}: {str(e)}")
                continue

        # Wait for all images to be sent
        for t in threads:
            t.join()

        if errors:
            return jsonify(
                {
                    "success": True,
                    "message": f"QR codes sent to {len(threads)} discovered devices",
                    "warnings": errors,
                }
            )
        else:
            return jsonify(
                {
                    "success": True,
                    "message": f"QR codes sent to {len(threads)} discovered devices",
                }
            )

    except Exception as e:
        return jsonify({"error": f"Failed to start QR positioning: {str(e)}"}), 500


@app.route("/positioning/analyze", methods=["POST"])
def analyze_positioning_photo():
    """Analyze uploaded photo to determine screen positions."""
    if not controller:
        return jsonify({"error": "Controller not initialized"}), 500

    if "photo" not in request.files:
        return jsonify({"error": "No photo uploaded"}), 400

    file = request.files["photo"]
    if file.filename == "":
        return jsonify({"error": "No photo selected"}), 400

    if not allowed_file(file.filename):
        return (
            jsonify({"error": "Invalid file type. Please upload an image file."}),
            400,
        )

    try:
        from ..perspective_correction import correct_perspective_distortion
        from ..position_detection import (
            calculate_physical_positions,
            detect_qr_positions,
            generate_updated_config,
        )

        # Open image and fix EXIF orientation
        image = PIL.Image.open(file.stream)
        corrected_image = fix_image_orientation(image)

        # Save debug image for analysis
        import datetime

        debug_filename = (
            f"/tmp/qr_analysis_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        )
        corrected_image.save(debug_filename, quality=95)
        logger.debug(f"Saved QR analysis image to {debug_filename}")

        # Get DHCP discovered devices for comparison
        from ..qr_generation import discover_devices_from_dhcp

        dhcp_devices = discover_devices_from_dhcp()
        dhcp_ips = {device.ip for device in dhcp_devices}

        # Detect QR codes from EXIF-corrected PIL image
        position_data = detect_qr_positions(corrected_image)

        if not position_data:
            return (
                jsonify(
                    {"error": "No QR codes detected in the photo", "can_apply": False}
                ),
                400,
            )

        # Apply perspective correction using rectangular screen constraints
        corrected_position_data = correct_perspective_distortion(position_data)

        # Use corrected data for position calculations
        position_data = [
            corrected.original._replace(
                center=corrected.corrected_center,
                corners=corrected.corrected_corners,
                screen_corners=corrected.corrected_screen_corners,
            )
            for corrected in corrected_position_data
        ]

        # Calculate physical positions
        physical_positions = calculate_physical_positions(
            position_data, controller.config
        )

        if not physical_positions:
            return (
                jsonify(
                    {
                        "error": "Could not calculate physical positions",
                        "can_apply": False,
                    }
                ),
                400,
            )

        # Check for missing devices
        detected_ips = set(physical_positions.keys())
        missing_ips = dhcp_ips - detected_ips
        has_missing_devices = len(missing_ips) > 0

        # Generate updated configuration
        updated_config = generate_updated_config(controller.config, physical_positions)

        # Convert config to YAML for preview
        import yaml

        yaml_preview = yaml.dump(updated_config, default_flow_style=False, indent=2)

        response_data = {
            "success": True,
            "message": f"Detected {len(position_data)} screens",
            "detected_devices": list(physical_positions.keys()),
            "positions": physical_positions,
            "config": updated_config,
            "yaml_preview": yaml_preview,
            "can_apply": True,
            "dhcp_devices": list(dhcp_ips),
            "missing_devices": list(missing_ips),
            "has_missing_devices": has_missing_devices,
        }

        if has_missing_devices:
            response_data["warning"] = (
                f"Warning: {len(missing_ips)} devices found in DHCP but not detected in photo: {', '.join(missing_ips)}"
            )

        return jsonify(response_data)

    except Exception as e:
        return jsonify({"error": f"Failed to analyze photo: {str(e)}"}), 500


@app.route("/positioning/apply", methods=["POST"])
def apply_positioning_config():
    """Apply the detected positioning configuration."""
    data = request.get_json()
    if not data or "config" not in data:
        return jsonify({"error": "No configuration provided"}), 400

    # Check if user confirmed when there are missing devices
    if data.get("has_missing_devices", False) and not data.get("confirmed", False):
        return (
            jsonify(
                {
                    "error": "Confirmation required",
                    "message": "Some DHCP devices were not detected. Please confirm you want to proceed.",
                    "requires_confirmation": True,
                }
            ),
            400,
        )

    try:
        # Write updated configuration to devices.yaml
        import yaml

        # Get the devices file path (assuming it's in the working directory)
        devices_file = "devices.yaml"

        # Read existing config to preserve screen_types if they exist
        try:
            with open(devices_file, "r") as f:
                existing_config = yaml.safe_load(f)
        except FileNotFoundError:
            existing_config = {}

        # Update with new device positions
        updated_config = data["config"]
        if "screen_types" in existing_config:
            updated_config["screen_types"] = existing_config["screen_types"]

        # Write updated configuration
        with open(devices_file, "w") as f:
            yaml.dump(updated_config, f, default_flow_style=False, indent=2)

        # Reload controller and device monitor with new configuration
        reload_device_config(devices_file)

        # Restore saved image if available
        restored_image = False
        if last_image_state["image"] is not None:
            try:
                get_controller().send_image(last_image_state["image"])
                restored_image = True
                logger.info(
                    "Restored saved image after applying positioning configuration"
                )
            except Exception as e:
                logger.warning(f"Could not restore saved image: {e}")

        message = f"Configuration updated with {len(updated_config['devices'])} devices"
        if restored_image:
            message += ". Previous image restored to displays."

        # Flash success message for homepage display
        flash(message, "success")

        return jsonify({"success": True})

    except Exception as e:
        return jsonify({"error": f"Failed to apply configuration: {str(e)}"}), 500


@app.route("/positioning/layout-preview")
def positioning_layout_preview():
    """Generate layout preview for detected positions."""
    if "detected_config" not in request.args:
        return "No detected configuration", 400

    try:
        import json

        detected_config = json.loads(request.args.get("detected_config"))

        # Create temporary config from detected positions
        import io

        from ..models import Config, Coordinates, DetectedDimensions, Device

        devices = []
        for device_data in detected_config.get("devices", []):
            try:
                screen_type_name = device_data["screen_type"]
                if screen_type_name not in SCREEN_TYPES:
                    raise ValueError(f"Unknown screen type: {screen_type_name}")
                device = Device(
                    host=device_data["host"],  # hostname stored in host field
                    screen_type=screen_type_name,
                    coordinates=Coordinates(
                        x=device_data["coordinates"]["x"],
                        y=device_data["coordinates"]["y"],
                    ),
                    detected_dimensions=DetectedDimensions(
                        width=device_data["detected_dimensions"]["width"],
                        height=device_data["detected_dimensions"]["height"],
                    ),
                    rotation=device_data.get("rotation", 0),
                )
                devices.append(device)
            except KeyError as e:
                logger.error(f"Unknown screen type in preview: {e}")
                continue

        if not devices:
            return "No valid devices in configuration", 400

        temp_config = Config(devices=devices)

        # Generate layout visualization
        buffer = io.BytesIO()
        temp_config.draw_rectangles_to_buffer(buffer)
        buffer.seek(0)

        return send_file(
            buffer,
            mimetype="image/png",
            as_attachment=False,
            download_name="detected_layout.png",
        )

    except Exception as e:
        logger.error(f"Error generating layout preview: {e}")
        return f"Error generating layout preview: {str(e)}", 500


@app.route("/layout")
def layout():
    """Generate and return the device layout visualization."""
    if not controller:
        return "Controller not initialized", 500

    # Generate layout image with last image overlay if available
    img_buffer = io.BytesIO()

    if last_image_state["refit_image"] and last_image_state["px_in_unit"]:
        controller.config.draw_rectangles_to_buffer(
            img_buffer, last_image_state["refit_image"], last_image_state["px_in_unit"]
        )
    else:
        controller.config.draw_rectangles_to_buffer(img_buffer)

    img_buffer.seek(0)
    return send_file(img_buffer, mimetype="image/png", as_attachment=False)


@app.route("/layout-data")
def layout_data():
    """Get screen layout data as JSON for canvas operations."""
    try:
        # Get the current processed source image if available
        image_size = None
        if controller:
            processed_image = controller.get_processed_source_image()
            if processed_image is not None:
                image_size = {
                    "width": processed_image.size[0],
                    "height": processed_image.size[1],
                }

        # Get screen layout information using controller's layout calculation
        screens = []
        if (
            controller
            and controller.config
            and controller.config.devices
            and last_image_state["image"] is not None
        ):
            # Use the controller's exact layout calculation method
            _, mm_to_px_ratio, device_rects_px, _ = controller.get_layout_info(
                last_image_state["image"]
            )

            # Convert device rectangles to screen info format
            for device, device_rect_px in device_rects_px.items():
                screen_info = {
                    "hostname": device.host,
                    "screen_type": device.screen_type,
                    "x": device_rect_px.start.x,
                    "y": device_rect_px.start.y,
                    "width": device_rect_px.dimensions.width,
                    "height": device_rect_px.dimensions.height,
                    "rotation": device.rotation,
                }
                screens.append(screen_info)

        response_data = {
            "image_size": image_size,
            "screens": screens,
            "scale_factor": last_image_state.get("px_in_unit", 1.0),
            "use_server_rendering": USE_SERVER_SIDE_RENDERING,
        }

        # Create ETag by hashing the dict representation
        md5_hash = hashlib.md5(f"{response_data}".encode("utf-8")).hexdigest()
        etag = f'"{md5_hash}"'

        # Check if client has the same version
        client_etag = request.headers.get("If-None-Match")
        if client_etag == etag:
            return "", 304  # Not Modified

        response = jsonify(response_data)
        response.headers["ETag"] = etag
        response.headers["Cache-Control"] = "private, max-age=0, must-revalidate"
        return response

    except Exception as e:
        logger.error(f"Error getting layout data: {e}")
        return jsonify(
            {"image_size": None, "screens": [], "scale_factor": 1.0, "error": str(e)}
        )


@app.route("/current-image")
def current_image():
    """Serve the processed source image that gets distributed to devices."""
    try:
        if not controller:
            # No controller available - return 204 No Content
            return "", 204

        # Get the processed source image from controller
        processed_image = controller.get_processed_source_image()
        if processed_image is None:
            # No processed image available - return 204 No Content
            return "", 204

        # Get PNG data from cache (will auto-update if image changed)
        img_data, etag = image_cache.get_png_data(processed_image)
        if img_data is None or etag is None:
            # Should not happen, but handle gracefully
            return "", 204

        # Check if client has the same version
        client_etag = request.headers.get("If-None-Match")
        if client_etag == etag:
            return "", 304  # Not Modified

        # Create buffer for sending
        img_buffer = io.BytesIO(img_data)
        response = send_file(img_buffer, mimetype="image/png")

        # Add caching headers
        response.headers["ETag"] = etag
        response.headers["Cache-Control"] = "private, max-age=0, must-revalidate"
        return response

    except Exception as e:
        logger.error(f"Error serving current image: {e}")
        return jsonify({"error": "Failed to generate image"}), 500


@app.route("/layout-image")
def layout_image():
    """Serve a server-side rendered layout image with screen rectangles."""
    try:
        if not controller or not controller.config or not controller.config.devices:
            return "", 404

        # Use the exact same logic as the controller
        device_rectangles = {}
        for device in controller.config.devices:
            start = Point(x=device.coordinates.x, y=device.coordinates.y)
            dimensions = Dimensions(
                width=device.detected_dimensions.width,
                height=device.detected_dimensions.height,
            )
            device_rectangles[device] = Rectangle(
                start=start,
                dimensions=dimensions,
            )

        # Calculate bounding rectangle exactly like the controller
        bounding_rectangle = Rectangle.bounding_rectangle(
            list(device_rectangles.values())
        )

        # Use the scaled image if available, otherwise create a white background
        if last_image_state["refit_image"] is not None:
            scaled_image = last_image_state["refit_image"].copy()
        else:
            # Create a white background scaled to the bounding rectangle
            scaled_image, _ = controller._scale_image_to_layout(
                PIL.Image.new("RGB", (800, 600), "white"), bounding_rectangle.dimensions
            )

        # Get mm_to_px_ratio scaling factor
        mm_to_px_ratio = last_image_state.get("px_in_unit")

        # If no image has been processed, return a simple placeholder
        if mm_to_px_ratio is None:
            mm_to_px_ratio = 1.0  # Default scale for placeholder

        # Create visualization by drawing screen rectangles
        layout_image = create_layout_visualization(
            scaled_image, device_rectangles, mm_to_px_ratio
        )

        # Convert to bytes and serve
        img_buffer = io.BytesIO()
        layout_image.save(img_buffer, format="PNG")
        img_buffer.seek(0)
        return send_file(img_buffer, mimetype="image/png")

    except Exception as e:
        logger.error(f"Error serving layout image: {e}")
        return "", 500


@app.route("/upload", methods=["POST"])
def upload_image():
    """Handle image upload and send to devices."""
    if "image" not in request.files:
        flash("No image file provided")
        return redirect(url_for("index"))

    file = request.files["image"]
    if file.filename == "":
        flash("No file selected")
        return redirect(url_for("index"))

    if not allowed_file(file.filename):
        flash("Invalid file type. Please upload an image file.")
        return redirect(url_for("index"))

    try:
        # Open and fix EXIF orientation
        image = PIL.Image.open(file.stream)
        image = fix_image_orientation(image)

        # Send to devices first
        get_controller().send_image(image)

        # Only save for layout overlay if send was successful
        save_last_image(image)

        flash(
            f"Successfully sent image to {len(get_controller().config.devices)} devices!"
        )
        return redirect(url_for("index"))

    except Exception as e:
        flash(f"Error processing image: {str(e)}")
        return redirect(url_for("index"))


@app.route("/api/upload", methods=["POST"])
def api_upload_image():
    """API endpoint for uploading and displaying images on screens."""
    try:
        # Check if image file is present
        if "image" not in request.files:
            return jsonify({"error": "No image file provided"}), 400

        file = request.files["image"]
        if file.filename == "":
            return jsonify({"error": "No file selected"}), 400

        if not allowed_file(file.filename):
            return (
                jsonify({"error": "Invalid file type. Please upload an image file."}),
                400,
            )

        if not controller:
            return jsonify({"error": "Controller not initialized"}), 500

        # Open and fix EXIF orientation
        image = PIL.Image.open(file.stream)
        image = fix_image_orientation(image)

        # Send to devices
        controller.send_image(image)

        # Save for layout overlay
        save_last_image(image)

        # Return success response with device info
        response_data = {
            "success": True,
            "message": f"Successfully sent image to {len(controller.config.devices)} devices",
            "devices_updated": len(controller.config.devices),
            "filename": file.filename,
            "image_size": {"width": image.size[0], "height": image.size[1]},
        }

        return jsonify(response_data), 200

    except Exception as e:
        return (
            jsonify({"error": "Failed to process and send image", "details": str(e)}),
            500,
        )


@app.route("/devices")
def devices_info():
    """Return device information as JSON."""
    if not controller:
        return jsonify({"error": "Controller not initialized"}), 500

    devices = []
    for device in controller.config.devices:
        devices.append(
            {
                "host": device.host,
                "screen_type": device.screen_type,
                "coordinates": {"x": device.coordinates.x, "y": device.coordinates.y},
                "rotation": device.rotation,
                "dimensions": {
                    "width": device.detected_dimensions.width,
                    "height": device.detected_dimensions.height,
                },
            }
        )

    return jsonify({"devices": devices})


@app.route("/device-status")
def device_status():
    """Return device monitoring status as JSON."""
    if not device_monitor:
        return jsonify({"error": "Device monitor not initialized"}), 500

    statuses = device_monitor.get_all_statuses()

    # Convert DeviceStatus objects to dict for JSON serialization
    status_data = {}
    for host, status in statuses.items():
        status_data[host] = {
            "host": status.host,
            "online": status.online,
            "last_seen": status.last_seen.isoformat() if status.last_seen else None,
            "last_error": status.last_error,
            "width": status.width,
            "height": status.height,
            "temperature": status.temperature,
            "screen_model": status.screen_model,
            "current_version": status.current_version,
            "compile_date": status.compile_date,
            "compile_time": status.compile_time,
            "project_name": status.project_name,
            "idf_version": status.idf_version,
            "running_partition": status.running_partition,
            "next_partition": status.next_partition,
            "app_elf_sha256": status.app_elf_sha256,
            "ota_state": status.ota_state,
            "rollback_enabled": status.rollback_enabled,
            "response_time_ms": status.response_time_ms,
        }

    return jsonify(
        {
            "devices": status_data,
            "online_count": len(device_monitor.get_online_devices()),
            "offline_count": len(device_monitor.get_offline_devices()),
            "total_count": len(statuses),
        }
    )


@app.route("/clear", methods=["POST"])
def clear_screens():
    """Clear all device screens."""
    if not controller:
        return jsonify({"error": "Controller not initialized"}), 500

    try:
        controller.clear_devices()

        return jsonify(
            {
                "success": True,
                "message": f"Cleared {len(controller.config.devices)} devices",
            }
        )

    except Exception as e:
        return jsonify({"error": f"Failed to clear screens: {str(e)}"}), 500


@app.route("/restore-image", methods=["POST"])
def restore_last_image():
    """Restore the last saved image from disk."""
    if not controller:
        return jsonify({"error": "Controller not initialized"}), 500

    try:
        # Load the persisted image
        if load_persisted_image():
            # If image was loaded successfully, also send it to devices
            if last_image_state["image"] is not None:
                controller.send_image(last_image_state["image"])
                return jsonify(
                    {
                        "success": True,
                        "message": "Successfully restored and sent last image to devices",
                    }
                )
            else:
                return jsonify({"error": "Image loaded but not available"}), 500
        else:
            return jsonify({"error": "No saved image found to restore"}), 404

    except Exception as e:
        return jsonify({"error": f"Failed to restore image: {str(e)}"}), 500


def get_wallpaper_images(wallpapers_dir):
    """Get list of wallpaper images from wallpapers directory."""
    patterns = ["*.png", "*.jpg", "*.jpeg", "*.gif", "*.bmp", "*.tiff", "*.webp"]
    images = []
    for pattern in patterns:
        images.extend(glob.glob(os.path.join(wallpapers_dir, pattern)))
    return images


# Reddit wallpaper fetching moved to ScreensaverManager class


# Pixabay wallpaper fetching moved to ScreensaverManager class


# Screensaver worker moved to ScreensaverManager class


def start_screensaver_internal():
    """Start the screensaver (internal version for startup)."""
    if not controller or not screensaver_manager:
        raise Exception("Controller or screensaver manager not initialized")

    if screensaver_manager.is_active:
        raise Exception("Screensaver already active")

    # Starting screensaver automatically enables it
    settings = get_settings()
    settings.screensaver.enabled = True
    settings.save_to_file()

    config = get_screensaver_config()
    screensaver_manager.start(config)

    return f"Screensaver started with {config['type']} type"


@app.route("/screensaver/start", methods=["POST"])
def start_screensaver():
    """Start the screensaver."""
    if not controller or not screensaver_manager:
        return (
            jsonify({"error": "Controller or screensaver manager not initialized"}),
            500,
        )

    if screensaver_manager.is_active:
        return jsonify({"error": "Screensaver already active"}), 400

    try:
        message = start_screensaver_internal()
        return jsonify({"success": True, "message": message})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/screensaver/stop", methods=["POST"])
def stop_screensaver():
    """Stop the screensaver."""
    if not screensaver_manager or not screensaver_manager.is_active:
        return jsonify({"error": "Screensaver not active"}), 400

    try:
        screensaver_manager.stop()

        # Stopping screensaver automatically disables it
        settings = get_settings()
        settings.screensaver.enabled = False
        settings.save_to_file()

        return jsonify({"success": True, "message": "Screensaver stopped"})

    except Exception as e:
        return jsonify({"error": f"Failed to stop screensaver: {str(e)}"}), 500


@app.route("/screensaver/next", methods=["POST"])
def screensaver_next_image():
    """Display the next screensaver image immediately."""
    if not screensaver_manager:
        return jsonify({"error": "Screensaver manager not initialized"}), 500

    try:
        success = screensaver_manager.next_image()
        if success:
            return jsonify({"success": True, "message": "Next image displayed"})
        else:
            return jsonify({"error": "Failed to display next image"}), 400
    except Exception as e:
        return jsonify({"error": f"Failed to display next image: {str(e)}"}), 500


@app.route("/screensaver/status")
def screensaver_status():
    """Get screensaver status."""
    config = get_screensaver_config()
    status = {
        "active": screensaver_manager.is_active if screensaver_manager else False,
        "enabled": config["enabled"],
        "type": config["type"],
        "interval": config["interval"],
    }

    if config["type"] == "gallery":
        from .collections_manager import get_collection_path, get_collection_images

        selected_collection = config["gallery"]["selected_collection"]
        collections_dir = config["gallery"]["collections_dir"]

        # Try to get images from collection
        collection_path = get_collection_path(selected_collection, collections_dir)
        if collection_path:
            images = get_collection_images(collection_path)
        else:
            # Fallback to legacy wallpapers_dir
            images = get_wallpaper_images(config["gallery"]["wallpapers_dir"])

        status.update(
            {
                "wallpapers_dir": selected_collection,  # Use collection name for display
                "selected_collection": selected_collection,
                "image_count": len(images),
                "has_images": len(images) > 0,
            }
        )
    elif config["type"] == "reddit":
        status.update(
            {
                "wallpapers_dir": f"r/{config['reddit']['subreddit']}",
                "image_count": config["reddit"]["limit"],
                "has_images": True,  # Assume Reddit is available
            }
        )
    elif config["type"] == "pixabay":
        status.update(
            {
                "wallpapers_dir": f"Pixabay: {config['pixabay']['keywords']}",
                "image_count": config["pixabay"]["per_page"],
                "has_images": bool(config["pixabay"]["api_key"]),
                "has_api_key": bool(config["pixabay"]["api_key"]),
            }
        )

    return jsonify(status)


# Collections management routes (API only - used by curation system)


@app.route("/api/collections", methods=["GET"])
def api_list_collections():
    """List all collections."""
    from .collections_manager import list_collections

    try:
        settings = get_settings()
        collections_dir = settings.screensaver.gallery.collections_dir
        collections = list_collections(collections_dir)

        return jsonify(
            {
                "success": True,
                "collections": collections,
                "selected_collection": settings.screensaver.gallery.selected_collection,
            }
        )
    except Exception as e:
        logger.error(f"Error listing collections: {e}")
        return jsonify({"error": f"Failed to list collections: {str(e)}"}), 500


@app.route("/api/collections", methods=["POST"])
def api_create_collection():
    """Create a new collection."""
    from .collections_manager import create_collection

    data = request.get_json()
    if not data or "name" not in data:
        return jsonify({"error": "Collection name is required"}), 400

    try:
        settings = get_settings()
        collections_dir = settings.screensaver.gallery.collections_dir
        success, message = create_collection(data["name"], collections_dir)

        if success:
            return jsonify({"success": True, "message": message})
        else:
            return jsonify({"error": message}), 400
    except Exception as e:
        logger.error(f"Error creating collection: {e}")
        return jsonify({"error": f"Failed to create collection: {str(e)}"}), 500


@app.route("/api/collections/<collection_name>", methods=["DELETE"])
def api_delete_collection(collection_name):
    """Delete a collection."""
    from .collections_manager import delete_collection

    try:
        settings = get_settings()
        collections_dir = settings.screensaver.gallery.collections_dir

        # Warn if deleting the currently selected collection for screensaver
        warning = None
        if collection_name == settings.screensaver.gallery.selected_collection:
            warning = f"This collection is currently selected for the screensaver. You may want to select a different collection in Screensaver settings."

        success, message = delete_collection(collection_name, collections_dir)

        if success:
            result = {"success": True, "message": message}
            if warning:
                result["warning"] = warning
            return jsonify(result)
        else:
            return jsonify({"error": message}), 400
    except Exception as e:
        logger.error(f"Error deleting collection: {e}")
        return jsonify({"error": f"Failed to delete collection: {str(e)}"}), 500


@app.route("/api/collections/<collection_name>/rename", methods=["POST"])
def api_rename_collection(collection_name):
    """Rename a collection."""
    from .collections_manager import rename_collection

    data = request.get_json()
    if not data or "new_name" not in data:
        return jsonify({"error": "New collection name is required"}), 400

    try:
        settings = get_settings()
        collections_dir = settings.screensaver.gallery.collections_dir
        new_name = data["new_name"]

        success, message = rename_collection(collection_name, new_name, collections_dir)

        if success:
            # Update selected collection if we renamed it
            if collection_name == settings.screensaver.gallery.selected_collection:
                settings.screensaver.gallery.selected_collection = new_name
                settings.save_to_file()

            return jsonify({"success": True, "message": message, "new_name": new_name})
        else:
            return jsonify({"error": message}), 400
    except Exception as e:
        logger.error(f"Error renaming collection: {e}")
        return jsonify({"error": f"Failed to rename collection: {str(e)}"}), 500


@app.route("/api/collections/<collection_name>/select", methods=["POST"])
def api_select_collection(collection_name):
    """Select a collection as the active gallery."""
    from .collections_manager import get_collection_path

    try:
        settings = get_settings()
        collections_dir = settings.screensaver.gallery.collections_dir

        # Verify collection exists
        collection_path = get_collection_path(collection_name, collections_dir)
        if not collection_path:
            return jsonify(
                {"error": f"Collection '{collection_name}' does not exist"}
            ), 404

        # Update selected collection
        settings.screensaver.gallery.selected_collection = collection_name
        settings.save_to_file()

        # Restart screensaver if active
        if screensaver_manager and screensaver_manager.is_active:
            screensaver_manager.stop()
            config = get_screensaver_config()
            screensaver_manager.start(config)

        return jsonify(
            {
                "success": True,
                "message": f"Collection '{collection_name}' selected as active gallery",
            }
        )
    except Exception as e:
        logger.error(f"Error selecting collection: {e}")
        return jsonify({"error": f"Failed to select collection: {str(e)}"}), 500


@app.route("/api/collections/<collection_name>/images", methods=["GET"])
def api_list_collection_images(collection_name):
    """List images in a collection."""
    from .collections_manager import list_collection_images

    try:
        settings = get_settings()
        collections_dir = settings.screensaver.gallery.collections_dir
        images = list_collection_images(collection_name, collections_dir)

        if images is None:
            return jsonify(
                {"error": f"Collection '{collection_name}' does not exist"}
            ), 404

        return jsonify(
            {
                "success": True,
                "collection": collection_name,
                "images": images,
            }
        )
    except Exception as e:
        logger.error(f"Error listing collection images: {e}")
        return jsonify({"error": f"Failed to list images: {str(e)}"}), 500


@app.route("/api/collections/<collection_name>/images", methods=["POST"])
def api_upload_collection_image(collection_name):
    """Upload an image to a collection."""
    from .collections_manager import save_uploaded_image

    if "image" not in request.files:
        return jsonify({"error": "No image file provided"}), 400

    file = request.files["image"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    if not allowed_file(file.filename):
        return jsonify(
            {"error": "Invalid file type. Please upload an image file."}
        ), 400

    try:
        settings = get_settings()
        collections_dir = settings.screensaver.gallery.collections_dir
        success, message = save_uploaded_image(
            collection_name, file, file.filename, collections_dir
        )

        if success:
            return jsonify(
                {"success": True, "message": message, "filename": file.filename}
            )
        else:
            return jsonify({"error": message}), 400
    except Exception as e:
        logger.error(f"Error uploading image: {e}")
        return jsonify({"error": f"Failed to upload image: {str(e)}"}), 500


@app.route("/api/collections/<collection_name>/images/<filename>", methods=["DELETE"])
def api_delete_collection_image(collection_name, filename):
    """Delete an image from a collection."""
    from .collections_manager import delete_collection_image

    try:
        settings = get_settings()
        collections_dir = settings.screensaver.gallery.collections_dir
        success, message = delete_collection_image(
            collection_name, filename, collections_dir
        )

        if success:
            return jsonify({"success": True, "message": message})
        else:
            return jsonify({"error": message}), 400
    except Exception as e:
        logger.error(f"Error deleting image: {e}")
        return jsonify({"error": f"Failed to delete image: {str(e)}"}), 500


@app.route("/api/collections/<collection_name>/images/<filename>")
def api_get_collection_image(collection_name, filename):
    """Get an image from a collection."""
    from .collections_manager import get_collection_path

    try:
        settings = get_settings()
        collections_dir = settings.screensaver.gallery.collections_dir

        # Get collection path
        collection_path = get_collection_path(collection_name, collections_dir)
        if not collection_path:
            return jsonify(
                {"error": f"Collection '{collection_name}' does not exist"}
            ), 404

        # Validate filename (no path components)
        if "/" in filename or "\\" in filename or filename in [".", ".."]:
            return jsonify({"error": "Invalid filename"}), 400

        # Get image path
        image_path = collection_path / filename
        if not image_path.exists():
            return jsonify({"error": f"Image '{filename}' not found"}), 404

        # ETag based on filename + mtime
        stat = image_path.stat()
        etag = f'"{filename}-{int(stat.st_mtime)}"'

        if request.headers.get("If-None-Match") == etag:
            return "", 304

        response = send_file(str(image_path), mimetype=f"image/{image_path.suffix[1:]}")
        response.headers["ETag"] = etag
        response.headers["Cache-Control"] = "private, max-age=86400"
        return response
    except Exception as e:
        logger.error(f"Error serving image: {e}")
        return jsonify({"error": f"Failed to serve image: {str(e)}"}), 500


# =============================================================================
# Curation Routes (new system)
# =============================================================================


@app.route("/curation")
def curation_page():
    """Curation management page."""
    return render_template("curation.html")


@app.route("/api/curation/status")
def curation_status():
    """Get curation and screensaver v2 status."""
    if not curation_manager or not screensaver_v2:
        return jsonify({"error": "Curation system not initialized"}), 500

    settings = get_settings()
    staging_info = curation_manager.get_staging_info()
    curation_progress = curation_manager.get_curation_progress()

    return jsonify({
        "screensaver": {
            "active": screensaver_v2.is_active,
            "enabled": settings.screensaver_v2.enabled,
            "interval": settings.screensaver_v2.interval,
        },
        "curation": {
            "active": curation_manager.is_active,
            "interval": settings.curation.interval,
            "sources_count": len(settings.curation.sources),
            "in_progress": curation_progress is not None,
            "progress": curation_progress,
            "last_result": curation_manager.get_last_result(),
        },
        "staging": staging_info,
    })


@app.route("/api/curation/cancel", methods=["POST"])
def cancel_curation():
    """Cancel a running curation."""
    if not curation_manager:
        return jsonify({"error": "Curation manager not initialized"}), 500

    if curation_manager.cancel_curation():
        return jsonify({"success": True, "message": "Cancellation requested"})
    else:
        return jsonify({"error": "No curation in progress"}), 400


@app.route("/api/curation/curate", methods=["POST"])
def run_curation():
    """Run curation immediately."""
    if not curation_manager:
        return jsonify({"error": "Curation manager not initialized"}), 500

    data = request.get_json() or {}
    dry_run = data.get("dry_run", False)

    try:
        result = curation_manager.curate(dry_run=dry_run)
        return jsonify({
            "success": True,
            "staged_count": result.staged_count,
            "filtered_count": result.filtered_count,
            "total_candidates": result.total_candidates,
            "sources_summary": result.sources_summary,
            "dry_run": dry_run,
        })
    except Exception as e:
        logger.error(f"Curation failed: {e}")
        return jsonify({"error": f"Curation failed: {str(e)}"}), 500


@app.route("/api/curation/curate-stream")
def run_curation_stream():
    """Run curation with SSE progress streaming."""
    import json as json_module

    if not curation_manager:
        return jsonify({"error": "Curation manager not initialized"}), 500

    progress_queue = queue.Queue()

    def progress_callback(update):
        progress_queue.put({
            "type": "progress",
            "phase": update.phase,
            "source": f"{update.source_index}/{update.source_count}",
            "source_name": update.source_name,
            "image": f"{update.image_index}",
            "staged": update.staged_count,
            "filtered": update.filtered_count,
            "message": update.message,
        })

    def run_curation_with_progress():
        try:
            result = curation_manager.curate_with_progress(progress_callback)
            progress_queue.put({
                "type": "complete",
                "staged_count": result.staged_count,
                "filtered_count": result.filtered_count,
                "total_candidates": result.total_candidates,
                "errors": result.errors,
            })
        except Exception as e:
            progress_queue.put({"type": "error", "message": str(e)})

    # Start curation in background thread
    curation_thread = threading.Thread(target=run_curation_with_progress, daemon=True)
    curation_thread.start()

    def generate():
        while True:
            try:
                update = progress_queue.get(timeout=30)
                yield f"data: {json_module.dumps(update)}\n\n"

                if update.get("type") in ("complete", "error"):
                    break
            except queue.Empty:
                # Send heartbeat
                yield "data: {\"type\": \"heartbeat\"}\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@app.route("/api/curation/staging")
def staging_status():
    """Get staging directory status."""
    if not curation_manager:
        return jsonify({"error": "Curation manager not initialized"}), 500

    info = curation_manager.get_staging_info()
    playlist = curation_manager.staging.get_playlist()

    # Get images from favorites collection (for badge display)
    favorites = []
    for img_id in playlist:
        img_info = curation_manager.staging.db.get_image(img_id)
        if img_info and img_info.source_name == "favorites":
            favorites.append(img_id)

    return jsonify({
        "path": info["path"],
        "count": info["count"],
        "current_image_id": info["current_image_id"],
        "position": info["position"],
        "is_empty": info["is_empty"],
        "playlist": playlist,
        "favorites": favorites,  # Images from favorites collection
    })


@app.route("/api/curation/staging/image/<filename>")
def get_staging_image(filename):
    """Get an image from staging directory."""
    if not curation_manager:
        return jsonify({"error": "Curation manager not initialized"}), 500

    # Validate filename
    if "/" in filename or "\\" in filename or filename in [".", ".."]:
        return jsonify({"error": "Invalid filename"}), 400

    image_path = curation_manager.staging.staging_path / filename
    if not image_path.exists():
        return jsonify({"error": f"Image '{filename}' not found"}), 404

    # ETag based on filename (UUIDs are unique) + mtime
    stat = image_path.stat()
    etag = f'"{filename}-{int(stat.st_mtime)}"'

    # Check If-None-Match
    if request.headers.get("If-None-Match") == etag:
        return "", 304

    response = send_file(str(image_path), mimetype="image/png")
    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "private, max-age=86400"
    return response


@app.route("/api/screensaver-v2/start", methods=["POST"])
def start_screensaver_v2():
    """Start the new curation-based screensaver."""
    if not screensaver_v2 or not curation_manager:
        return jsonify({"error": "Screensaver V2 not initialized"}), 500

    if screensaver_v2.is_active:
        return jsonify({"error": "Screensaver already active"}), 400

    data = request.get_json() or {}
    interval = data.get("interval", get_settings().screensaver_v2.interval)

    try:
        # Start curation manager background thread if not running
        if not curation_manager.is_active:
            curation_manager.start()

        screensaver_v2.start(interval=interval)

        # Update settings
        settings = get_settings()
        settings.screensaver_v2.enabled = True
        settings.screensaver_v2.interval = interval
        settings.save_to_file()

        return jsonify({
            "success": True,
            "message": f"Screensaver V2 started (interval: {interval}s)",
        })
    except Exception as e:
        logger.error(f"Failed to start screensaver v2: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/screensaver-v2/stop", methods=["POST"])
def stop_screensaver_v2():
    """Stop the new curation-based screensaver."""
    if not screensaver_v2:
        return jsonify({"error": "Screensaver V2 not initialized"}), 500

    if not screensaver_v2.is_active:
        return jsonify({"error": "Screensaver not active"}), 400

    try:
        screensaver_v2.stop()

        # Update settings
        settings = get_settings()
        settings.screensaver_v2.enabled = False
        settings.save_to_file()

        return jsonify({"success": True, "message": "Screensaver V2 stopped"})
    except Exception as e:
        logger.error(f"Failed to stop screensaver v2: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/screensaver-v2/next", methods=["POST"])
def screensaver_v2_next():
    """Display the next image immediately."""
    if not screensaver_v2:
        return jsonify({"error": "Screensaver V2 not initialized"}), 500

    try:
        success = screensaver_v2.next_image()
        if success:
            return jsonify({"success": True, "message": "Next image displayed"})
        else:
            return jsonify({"error": "Failed to display next image"}), 400
    except Exception as e:
        logger.error(f"Failed to show next image: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/curation/reject-current", methods=["POST"])
def reject_current_image():
    """Reject the current image and skip to next."""
    if not curation_manager:
        return jsonify({"error": "Curation manager not initialized"}), 500

    try:
        # Get current image filename
        current = curation_manager.staging.get_current_image_filename()
        if not current:
            return jsonify({"error": "No current image to reject"}), 400

        # Add to rejected list
        curation_manager.staging.reject_image(current)

        # If screensaver is active, advance to next image
        if screensaver_v2 and screensaver_v2.is_active:
            screensaver_v2.next_image()

        return jsonify({
            "success": True,
            "message": f"Rejected {current}",
            "rejected_count": len(curation_manager.staging.get_rejected_list()),
        })
    except Exception as e:
        logger.error(f"Failed to reject image: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/curation/show", methods=["POST"])
def show_staged_image():
    """Show a specific staged image on displays now."""
    if not curation_manager or not controller:
        return jsonify({"error": "Not initialized"}), 500

    data = request.get_json()
    if not data or "filename" not in data:
        return jsonify({"error": "Filename required"}), 400

    try:
        filename = data["filename"]
        image_path = curation_manager.staging.staging_path / filename

        if not image_path.exists():
            return jsonify({"error": f"Image not found: {filename}"}), 404

        # Load and send to displays
        img = PIL.Image.open(image_path)
        img.load()
        controller.send_image(img)
        save_last_image(img)

        return jsonify({"success": True, "message": "Image sent to displays"})
    except Exception as e:
        logger.error(f"Failed to show image: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/curation/reject", methods=["POST"])
def reject_image_by_filename():
    """Reject a specific image by filename."""
    if not curation_manager:
        return jsonify({"error": "Curation manager not initialized"}), 500

    data = request.get_json()
    if not data or "filename" not in data:
        return jsonify({"error": "Filename required"}), 400

    try:
        filename = data["filename"]
        curation_manager.staging.reject_image(filename)

        return jsonify({
            "success": True,
            "message": f"Rejected {filename}",
        })
    except Exception as e:
        logger.error(f"Failed to reject image: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/curation/like", methods=["POST"])
def like_image():
    """Like an image - save to favorites collection."""
    if not curation_manager:
        return jsonify({"error": "Curation manager not initialized"}), 500

    data = request.get_json()
    if not data or "filename" not in data:
        return jsonify({"error": "Filename required"}), 400

    try:
        filename = data["filename"]
        staging_path = curation_manager.staging.staging_path / filename

        if not staging_path.exists():
            return jsonify({"error": f"Image not found: {filename}"}), 404

        # Mark as liked in database
        curation_manager.staging.like_image(filename)

        # Ensure favorites collection exists
        from .collections_manager import create_collection, get_collection_path

        settings = get_settings()
        collections_dir = settings.screensaver.gallery.collections_dir

        favorites_path = get_collection_path("favorites", collections_dir)
        if not favorites_path:
            create_collection("favorites", collections_dir)
            favorites_path = get_collection_path("favorites", collections_dir)

        # Copy image to favorites
        import shutil
        dest_path = favorites_path / filename
        shutil.copy2(staging_path, dest_path)

        return jsonify({
            "success": True,
            "message": f"Saved to favorites",
        })
    except Exception as e:
        logger.error(f"Failed to like image: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/curation/rejected")
def get_rejected_images():
    """Get list of rejected images with metadata."""
    if not curation_manager:
        return jsonify({"error": "Curation manager not initialized"}), 500

    try:
        rejected_ids = curation_manager.staging.get_rejected_list()
        rejected = []
        for img_id in rejected_ids:
            info = curation_manager.staging.get_image_info(img_id)
            if info:
                rejected.append(info)
        return jsonify({"success": True, "rejected": rejected})
    except Exception as e:
        logger.error(f"Failed to get rejected: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/curation/unreject", methods=["POST"])
def unreject_image():
    """Restore a rejected image (remove from rejection list)."""
    if not curation_manager:
        return jsonify({"error": "Curation manager not initialized"}), 500

    data = request.get_json()
    if not data or "image_id" not in data:
        return jsonify({"error": "image_id required"}), 400

    try:
        image_id = data["image_id"]
        # Set status back to 'active' (or could delete the record)
        curation_manager.staging.db.set_status(image_id, "active")
        return jsonify({"success": True, "message": f"Unrejected {image_id}"})
    except Exception as e:
        logger.error(f"Failed to unreject: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/curation/stats")
def get_curation_stats():
    """Get curation database statistics."""
    if not curation_manager:
        return jsonify({"error": "Curation manager not initialized"}), 500

    try:
        stats = curation_manager.staging.get_stats()
        return jsonify({
            "success": True,
            "stats": stats,
        })
    except Exception as e:
        logger.error(f"Failed to get stats: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/curation/image-info/<filename>")
def get_image_info(filename):
    """Get metadata for a specific image."""
    if not curation_manager:
        return jsonify({"error": "Curation manager not initialized"}), 500

    try:
        info = curation_manager.staging.get_image_info(filename)
        if info:
            return jsonify({"success": True, "info": info})
        else:
            return jsonify({"error": f"Image not found: {filename}"}), 404
    except Exception as e:
        logger.error(f"Failed to get image info: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/curation/config")
def get_curation_config():
    """Get current curation configuration."""
    settings = get_settings()
    curation = settings.curation
    target_ratio = get_layout_aspect_ratio()

    return jsonify({
        "staging_path": curation.staging_path,
        "count": curation.count,
        "shuffle": curation.shuffle,
        "interval": curation.interval,
        "filters": {
            "enabled": curation.filters.enabled,
            "min_width": curation.filters.min_width,
            "min_height": curation.filters.min_height,
            "min_contrast": curation.filters.min_contrast,
            "min_entropy": curation.filters.min_histogram_entropy,
            "min_coverage_enabled": curation.filters.min_coverage_enabled,
            "min_coverage": curation.filters.min_coverage,
            "keywords_exclude": curation.filters.keywords_exclude,
            "avoid_seam": curation.filters.avoid_seam,
        },
        "target_aspect_ratio": round(target_ratio, 2) if target_ratio else None,
        "sources": [s.model_dump() for s in curation.sources],
    })


@app.route("/api/curation/config", methods=["POST"])
def update_curation_config():
    """Update curation configuration."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    try:
        settings = get_settings()

        # Update basic settings
        if "count" in data:
            settings.curation.count = int(data["count"])
        if "shuffle" in data:
            settings.curation.shuffle = bool(data["shuffle"])
        if "interval" in data:
            settings.curation.interval = int(data["interval"])

        # Update filters
        if "filters" in data:
            f = data["filters"]
            if "enabled" in f:
                settings.curation.filters.enabled = bool(f["enabled"])
            if "min_width" in f:
                settings.curation.filters.min_width = int(f["min_width"])
            if "min_height" in f:
                settings.curation.filters.min_height = int(f["min_height"])
            if "min_contrast" in f:
                settings.curation.filters.min_contrast = int(f["min_contrast"])
            if "min_entropy" in f:
                settings.curation.filters.min_histogram_entropy = f["min_entropy"]
            if "min_coverage_enabled" in f:
                settings.curation.filters.min_coverage_enabled = bool(f["min_coverage_enabled"])
            if "min_coverage" in f:
                settings.curation.filters.min_coverage = float(f["min_coverage"])
            if "keywords_exclude" in f:
                settings.curation.filters.keywords_exclude = f["keywords_exclude"]
            if "avoid_seam" in f:
                settings.curation.filters.avoid_seam = bool(f["avoid_seam"])

        # Update sources (replace entirely)
        if "sources" in data:
            from ..settings import (
                CollectionSourceSettings,
                RedditSourceSettings,
            )

            new_sources = []
            for s in data["sources"]:
                if s["type"] == "collection":
                    new_sources.append(CollectionSourceSettings(**s))
                elif s["type"] == "reddit":
                    new_sources.append(RedditSourceSettings(**s))
            settings.curation.sources = new_sources

        settings.save_to_file()

        # Reconfigure curation manager
        if curation_manager:
            collections_dir = settings.screensaver.gallery.collections_dir
            config = settings.curation.to_manager_config(
                collections_dir=collections_dir,
                target_aspect_ratio=get_layout_aspect_ratio(),
            )
            curation_manager.configure_from_dict(config)

        return jsonify({"success": True, "message": "Configuration updated"})
    except Exception as e:
        logger.error(f"Failed to update config: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/curation/sources", methods=["POST"])
def add_curation_source():
    """Add a new source."""
    data = request.get_json()
    if not data or "type" not in data:
        return jsonify({"error": "Source type required"}), 400

    try:
        settings = get_settings()

        from ..settings import (
            CollectionSourceSettings,
            RedditSourceSettings,
        )

        if data["type"] == "collection":
            source = CollectionSourceSettings(
                name=data.get("name", "wallpapers"),
            )
        elif data["type"] == "reddit":
            source = RedditSourceSettings(
                subreddits=data.get("subreddits", ["wallpapers"]),
                sort=data.get("sort", "top"),
                time_period=data.get("time_period", "week"),
                limit=data.get("limit", 30),
            )
        else:
            return jsonify({"error": f"Unknown source type: {data['type']}"}), 400

        settings.curation.sources.append(source)
        settings.save_to_file()

        # Reconfigure curation manager
        if curation_manager:
            collections_dir = settings.screensaver.gallery.collections_dir
            config = settings.curation.to_manager_config(
                collections_dir=collections_dir,
                target_aspect_ratio=get_layout_aspect_ratio(),
            )
            curation_manager.configure_from_dict(config)

        return jsonify({"success": True, "message": "Source added"})
    except Exception as e:
        logger.error(f"Failed to add source: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/curation/sources/<int:index>", methods=["DELETE"])
def delete_curation_source(index):
    """Delete a source by index."""
    try:
        settings = get_settings()

        if index < 0 or index >= len(settings.curation.sources):
            return jsonify({"error": "Invalid source index"}), 400

        settings.curation.sources.pop(index)
        settings.save_to_file()

        # Reconfigure curation manager
        if curation_manager:
            collections_dir = settings.screensaver.gallery.collections_dir
            config = settings.curation.to_manager_config(
                collections_dir=collections_dir,
                target_aspect_ratio=get_layout_aspect_ratio(),
            )
            curation_manager.configure_from_dict(config)

        return jsonify({"success": True, "message": "Source deleted"})
    except Exception as e:
        logger.error(f"Failed to delete source: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/flash/start", methods=["POST"])
def start_flash():
    """Start the firmware flashing process."""
    if not flash_manager:
        return jsonify({"error": "Flash manager not initialized"}), 500

    data = request.get_json()
    if not data or "screen_type" not in data:
        return jsonify({"error": "Screen type is required"}), 400

    screen_type = data["screen_type"]
    if screen_type not in SCREEN_TYPES:
        return jsonify({"error": f"Invalid screen type: {screen_type}"}), 400

    result = flash_manager.start_flash(screen_type)

    if result["success"]:
        return jsonify(result)
    else:
        return jsonify(result), 500


@app.route("/flash/output/<process_id>")
def flash_output_stream(process_id):
    """Stream the output of a flash process."""
    if not flash_manager:
        return jsonify({"error": "Flash manager not initialized"}), 500

    flash_process = flash_manager.get_process_output(process_id)
    if not flash_process:
        return jsonify({"error": "Process not found"}), 404

    def generate():
        output_queue = flash_process.output_queue

        while True:
            try:
                # Get output with timeout
                line = output_queue.get(timeout=1.0)
                yield f"data: {line}\n\n"

                # Check if process finished
                if flash_process.finished and output_queue.empty():
                    yield f"event: finished\ndata: {flash_process.return_code}\n\n"
                    break

            except queue.Empty:
                # Send heartbeat to keep connection alive
                if flash_process.finished:
                    yield f"event: finished\ndata: {flash_process.return_code}\n\n"
                    break
                else:
                    yield "data: \n\n"  # Heartbeat

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@app.route("/flash/stop/<process_id>", methods=["POST"])
def stop_flash(process_id):
    """Stop a running flash process."""
    if not flash_manager:
        return jsonify({"error": "Flash manager not initialized"}), 500

    result = flash_manager.stop_process(process_id)

    if result["success"]:
        return jsonify(result)
    else:
        return jsonify(result), 500


def create_app(devices_file="devices.yaml"):
    """Create Flask app with configuration."""
    global \
        controller, \
        screensaver_manager, \
        curation_manager, \
        screensaver_v2, \
        ota_manager, \
        device_monitor, \
        flash_manager, \
        process_manager
    if controller is None:
        controller = TapestryController.from_config_file(devices_file)

    def send_and_save_image(image):
        """Send image to displays and save for current-image endpoint."""
        controller.send_image(image)
        save_last_image(image)
        # Don't update cache for screensaver images - they're temporary

    if screensaver_manager is None:
        screensaver_manager = ScreensaverManager(send_and_save_image)

    # Initialize new curation system
    if curation_manager is None:
        settings = get_settings()
        curation_manager = CurationManager(
            staging_path=settings.curation.staging_path,
            curation_interval=settings.curation.interval,
        )
        # Configure from settings
        collections_dir = settings.screensaver.gallery.collections_dir
        config = settings.curation.to_manager_config(
                collections_dir=collections_dir,
                target_aspect_ratio=get_layout_aspect_ratio(),
            )
        curation_manager.configure_from_dict(config)

    if screensaver_v2 is None:
        screensaver_v2 = ScreensaverV2(curation_manager, send_and_save_image)
    if process_manager is None:
        process_manager = ProcessManager()
    if ota_manager is None:
        ota_manager = OTAManager(process_manager=process_manager)
    if flash_manager is None:
        flash_manager = FlashManager(process_manager=process_manager)
    if device_monitor is None:
        config = MonitorConfig(poll_interval=30, request_timeout=5, enabled=True)
        device_monitor = DeviceMonitor(config)
        # Start monitoring devices from controller config
        device_hosts = [device.host for device in controller.config.devices]
        device_monitor.start_monitoring(device_hosts)

    # Ensure default collection exists and migrate legacy wallpapers if needed
    from .collections_migration import migrate_legacy_wallpapers_if_needed

    migration_result = migrate_legacy_wallpapers_if_needed()
    if migration_result["migrated"]:
        logger.info(
            "Migrated legacy wallpapers to collections system. "
            "Your images are now in the 'wallpapers' collection."
        )

    return app


# OTA Update Routes


@app.route("/ota")
def ota_page():
    """OTA firmware update page."""
    return render_template("ota.html")


@app.route("/ota/build", methods=["POST"])
def ota_build():
    """Build firmware for OTA update."""
    if not ota_manager:
        return jsonify({"error": "OTA manager not initialized"}), 500

    result = ota_manager.build_firmware()

    if result["success"]:
        return jsonify(result)
    else:
        return jsonify(result), 500


@app.route("/ota/upload", methods=["POST"])
def ota_upload():
    """Upload firmware to device via OTA."""
    if not ota_manager:
        return jsonify({"error": "OTA manager not initialized"}), 500

    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    device_ip = data["device"]
    force_update = data["force_update"]

    result = ota_manager.upload_firmware(device_ip, force_update)

    if result["success"]:
        return jsonify(result)
    else:
        return jsonify(result), 500


@app.route("/ota/build-stream", methods=["POST"])
def ota_build_stream():
    """Start streaming OTA firmware build process."""
    if not ota_manager:
        return jsonify({"error": "OTA manager not initialized"}), 500

    result = ota_manager.start_streaming_build()

    if result["success"]:
        return jsonify(result)
    else:
        return jsonify(result), 500


@app.route("/ota/output/<process_id>")
def ota_output_stream(process_id):
    """Stream the output of an OTA build process."""
    if not ota_manager:
        return jsonify({"error": "OTA manager not initialized"}), 500

    streaming_process = ota_manager.get_streaming_process(process_id)
    if not streaming_process:
        return jsonify({"error": "Process not found"}), 404

    def generate():
        output_queue = streaming_process.output_queue

        while True:
            try:
                # Get output with timeout
                line = output_queue.get(timeout=1.0)
                yield f"data: {line}\n\n"

                # Check if process finished
                if streaming_process.finished and output_queue.empty():
                    yield f"event: finished\ndata: {streaming_process.return_code}\n\n"
                    break

            except queue.Empty:
                # Send heartbeat to keep connection alive
                if streaming_process.finished:
                    yield f"event: finished\ndata: {streaming_process.return_code}\n\n"
                    break
                else:
                    yield "data: \n\n"  # Heartbeat

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@app.route("/ota/stop/<process_id>", methods=["POST"])
def ota_stop_build(process_id):
    """Stop a running OTA build process."""
    if not ota_manager:
        return jsonify({"error": "OTA manager not initialized"}), 500

    result = ota_manager.stop_streaming_process(process_id)

    if result["success"]:
        return jsonify(result)
    else:
        return jsonify(result), 500


def parse_args():
    parser = argparse.ArgumentParser(description="Start Tapestry Web UI")
    parser.add_argument(
        "--devices-file",
        default="devices.yaml",
        help="YAML file containing device configuration",
    )
    parser.add_argument(
        "--host", default="::", help="Host to bind to (default: :: for IPv4+IPv6)"
    )
    parser.add_argument(
        "--port", type=int, default=5000, help="Port to bind to (default: 5000)"
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    return parser.parse_args()


def main():
    """Main entry point for web UI."""
    args = parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="[%(levelname)s] %(message)s",
    )

    settings = get_settings()

    # Initialize via create_app to avoid duplication
    create_app(args.devices_file)

    settings = get_settings()

    # Auto-start screensaver v2 if enabled (new curation-based system)
    if settings.screensaver_v2.enabled:
        logger.info("Screensaver V2 is enabled, starting with curation system...")
        try:
            if curation_manager and not curation_manager.is_active:
                curation_manager.start()
            if screensaver_v2:
                screensaver_v2.start(interval=settings.screensaver_v2.interval)
                logger.info(f"Screensaver V2 started (interval: {settings.screensaver_v2.interval}s)")
        except Exception as e:
            logger.error(f"Failed to auto-start screensaver v2: {e}")
    # Legacy screensaver auto-start (if v2 not enabled)
    elif settings.screensaver.enabled:
        logger.info("Legacy screensaver is enabled in settings, starting automatically...")
        try:
            message = start_screensaver_internal()
            logger.info(f"Screensaver started successfully: {message}")
        except Exception as e:
            logger.error(f"Failed to auto-start screensaver: {e}")

    logger.info(
        f"Starting Tapestry Web UI with {len(get_controller().config.devices)} devices"
    )
    logger.info(f"Access at http://localhost:{args.port}")
    logger.info("Use 'Restore Last Image' button to load previous image")

    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
