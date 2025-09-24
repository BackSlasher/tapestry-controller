#!/usr/bin/env python3
import os
import io
import argparse
import hashlib
import logging
import time
import random
import glob
import threading
import subprocess
import queue
from flask import Flask, render_template, request, jsonify, send_file, flash, redirect, url_for, Response
from werkzeug.utils import secure_filename
import PIL.Image
from PIL import ExifTags, ImageDraw, ImageFont
from ..controller import TapestryController
from ..geometry import Point, Dimensions, Rectangle
from ..models import load_config
from ..screen_types import SCREEN_TYPES
from ..image_utils import image_refit, image_crop
from ..settings import get_settings, ScreensaverSettings, GallerySettings, RedditSettings

app = Flask(__name__)
app.config['SECRET_KEY'] = 'tapestry-webui-secret-key'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Set up logging
logger = logging.getLogger(__name__)

# Global controller instance
controller = None

# Runtime screensaver state (not persisted)
screensaver_runtime = {
    'active': False,
    'thread': None,
    'stop_event': None
}

def get_screensaver_config():
    """Get screensaver configuration from settings."""
    settings = get_settings()
    return {
        'enabled': settings.screensaver.enabled,
        'type': settings.screensaver.type,
        'interval': settings.screensaver.interval,
        'gallery': {
            'wallpapers_dir': settings.screensaver.gallery.wallpapers_dir
        },
        'reddit': {
            'subreddit': settings.screensaver.reddit.subreddit,
            'time_period': settings.screensaver.reddit.time_period,
            'sort': settings.screensaver.reddit.sort,
            'limit': settings.screensaver.reddit.limit
        }
    }

# Last image state
last_image_state = {
    'image': None,  # PIL Image object
    'refit_image': None,  # Processed/resized image
    'px_in_unit': None,  # Scaling factor
    'thumbnail_cache': None,  # Cached thumbnail for web display
    'thumbnail_max_size': (800, 600),  # Max thumbnail dimensions
}

# Configuration for layout rendering method
USE_SERVER_SIDE_RENDERING = False  # Set to False to use canvas-based rendering


def create_layout_visualization(scaled_image, device_rectangles, mm_to_px_ratio):
    """Create a layout visualization using the new simplified controller logic."""
    
    # Calculate bounding rectangle in mm (same as controller)
    bounding_rect_mm = Rectangle.bounding_rectangle(device_rectangles.values())
    
    # Start with the scaled image as the background
    layout_canvas = scaled_image.copy()
    draw = ImageDraw.Draw(layout_canvas)
    
    # For each device, show where it will be cropped from
    for device, rect_mm in device_rectangles.items():
        # Convert device position from mm to pixels (same as controller)
        device_rect_px = Rectangle(
            start=Point(
                x=int((rect_mm.start.x - bounding_rect_mm.start.x) * mm_to_px_ratio),
                y=int((rect_mm.start.y - bounding_rect_mm.start.y) * mm_to_px_ratio)
            ),
            dimensions=Dimensions(
                width=int(rect_mm.dimensions.width * mm_to_px_ratio),
                height=int(rect_mm.dimensions.height * mm_to_px_ratio)
            )
        )
        
        # Draw screen border at the exact position where cropping will occur
        x = device_rect_px.start.x
        y = device_rect_px.start.y
        width = device_rect_px.dimensions.width
        height = device_rect_px.dimensions.height
        
        # Draw red border to show the crop area
        draw.rectangle([x, y, x + width, y + height], outline='red', width=3)
        
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
                [text_bg_x, text_bg_y, text_bg_x + text_width + 4, text_bg_y + text_height + 4],
                fill=(255, 255, 255, 180)
            )
            draw.text((text_bg_x + 2, text_bg_y + 2), label, fill='black', font=font)
        except Exception as e:
            logger.error(f"Error drawing label for {device.host}: {e}")
    
    return layout_canvas

def allowed_file(filename):
    """Check if uploaded file has allowed extension."""
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'tiff'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_or_create_thumbnail():
    """Get cached thumbnail or create one from refit_image."""
    if last_image_state['thumbnail_cache'] is not None:
        return last_image_state['thumbnail_cache']
    
    if last_image_state['refit_image'] is None:
        return None
    
    # Create thumbnail
    img = last_image_state['refit_image'].copy()
    img.thumbnail(last_image_state['thumbnail_max_size'], PIL.Image.LANCZOS)
    
    # Cache it
    last_image_state['thumbnail_cache'] = img
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
                image = image.transpose(PIL.Image.FLIP_LEFT_RIGHT)
            elif orientation == 3:
                # 180 degree rotation
                image = image.rotate(180, expand=True)
            elif orientation == 4:
                # Vertical flip
                image = image.transpose(PIL.Image.FLIP_TOP_BOTTOM)
            elif orientation == 5:
                # Horizontal flip + 90 degree rotation
                image = image.transpose(PIL.Image.FLIP_LEFT_RIGHT)
                image = image.rotate(-90, expand=True)
            elif orientation == 6:
                # 90 degree rotation
                image = image.rotate(-90, expand=True)
            elif orientation == 7:
                # Horizontal flip + 270 degree rotation  
                image = image.transpose(PIL.Image.FLIP_LEFT_RIGHT)
                image = image.rotate(90, expand=True)
            elif orientation == 8:
                # 270 degree rotation
                image = image.rotate(90, expand=True)
                
    except Exception as e:
        logger.warning(f"Could not fix image orientation: {e}")
        # Return original image if EXIF processing fails
        pass
    
    return image

def load_persisted_image():
    """Load the last image from disk if it exists."""
    try:
        import os
        persist_dir = os.path.expanduser("~/.tapestry")
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
    from ..geometry import Point, Dimensions, Rectangle
    from ..image_utils import image_refit
    
    # Calculate device rectangles and bounding rectangle (same as controller does)
    device_rectangles = {}
    for device in controller.config.devices:
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
    bounding_rectangle = Rectangle.bounding_rectangle(device_rectangles.values())
    scaled_image, mm_to_px_ratio = controller._scale_image_to_layout(
        image, bounding_rectangle.dimensions
    )
    
    # Save to global state
    last_image_state['image'] = image.copy()
    last_image_state['refit_image'] = scaled_image.copy()  # Now using scaled_image
    last_image_state['px_in_unit'] = mm_to_px_ratio  # Now using mm_to_px_ratio
    last_image_state['thumbnail_cache'] = None  # Clear thumbnail cache
    
    # Persist to disk for restart recovery
    try:
        import os
        persist_dir = os.path.expanduser("~/.tapestry")
        os.makedirs(persist_dir, exist_ok=True)
        persist_path = os.path.join(persist_dir, "last_image.png")
        image.save(persist_path, "PNG")
    except Exception as e:
        logger.warning(f"Could not persist image: {e}")

@app.route('/')
def index():
    """Main page showing layout and upload form."""
    device_count = len(controller.config.devices) if controller else 0
    return render_template('index.html', device_count=device_count)

@app.route('/screensaver')
def screensaver_config():
    """Screensaver configuration page."""
    return render_template('screensaver.html')

@app.route('/flash')
def flash_firmware():
    """Flash firmware page."""
    return render_template('flash.html', screen_types=SCREEN_TYPES)

@app.route('/positioning')
def positioning():
    """QR-based positioning page."""
    return render_template('positioning.html')

@app.route('/positioning/qr-mode', methods=['POST'])
def start_qr_positioning():
    """Start QR positioning mode - display QR codes on all discovered devices."""
    try:
        from ..qr_generation import generate_all_positioning_qr_images
        from ..device import draw_unrotated
        
        # Discover devices from DHCP and generate QR codes
        qr_images = generate_all_positioning_qr_images()
        
        if not qr_images:
            return jsonify({'error': 'No devices discovered from DHCP leases. Ensure devices are connected and DHCP server is running.'}), 400
        
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
            return jsonify({
                'success': True,
                'message': f'QR codes sent to {len(threads)} discovered devices',
                'warnings': errors
            })
        else:
            return jsonify({
                'success': True,
                'message': f'QR codes sent to {len(threads)} discovered devices'
            })
            
    except Exception as e:
        return jsonify({'error': f'Failed to start QR positioning: {str(e)}'}), 500

@app.route('/positioning/analyze', methods=['POST'])
def analyze_positioning_photo():
    """Analyze uploaded photo to determine screen positions."""
    if not controller:
        return jsonify({'error': 'Controller not initialized'}), 500
    
    if 'photo' not in request.files:
        return jsonify({'error': 'No photo uploaded'}), 400
    
    file = request.files['photo']
    if file.filename == '':
        return jsonify({'error': 'No photo selected'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': 'Invalid file type. Please upload an image file.'}), 400
    
    try:
        from ..position_detection import detect_qr_positions, calculate_physical_positions, generate_updated_config
        
        # Open image and fix EXIF orientation
        image = PIL.Image.open(file.stream)
        corrected_image = fix_image_orientation(image)
        
        # Save debug image for analysis
        import datetime
        debug_filename = f"/tmp/qr_analysis_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        corrected_image.save(debug_filename, quality=95)
        logger.debug(f"Saved QR analysis image to {debug_filename}")
        
        # Get DHCP discovered devices for comparison
        from ..qr_generation import discover_devices_from_dhcp
        dhcp_devices = discover_devices_from_dhcp()
        dhcp_ips = {device.ip for device in dhcp_devices}
        
        # Detect QR codes from EXIF-corrected PIL image
        position_data = detect_qr_positions(corrected_image)
        
        if not position_data:
            return jsonify({
                'error': 'No QR codes detected in the photo',
                'can_apply': False
            }), 400
        
        # Calculate physical positions
        physical_positions = calculate_physical_positions(position_data, controller.config)
        
        if not physical_positions:
            return jsonify({
                'error': 'Could not calculate physical positions', 
                'can_apply': False
            }), 400
        
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
            'success': True,
            'message': f'Detected {len(position_data)} screens',
            'detected_devices': list(physical_positions.keys()),
            'positions': physical_positions,
            'config': updated_config,
            'yaml_preview': yaml_preview,
            'can_apply': True,
            'dhcp_devices': list(dhcp_ips),
            'missing_devices': list(missing_ips),
            'has_missing_devices': has_missing_devices
        }
        
        if has_missing_devices:
            response_data['warning'] = f"Warning: {len(missing_ips)} devices found in DHCP but not detected in photo: {', '.join(missing_ips)}"
        
        return jsonify(response_data)
        
    except Exception as e:
        return jsonify({'error': f'Failed to analyze photo: {str(e)}'}), 500

@app.route('/positioning/apply', methods=['POST'])
def apply_positioning_config():
    """Apply the detected positioning configuration."""
    data = request.get_json()
    if not data or 'config' not in data:
        return jsonify({'error': 'No configuration provided'}), 400
    
    # Check if user confirmed when there are missing devices
    if data.get('has_missing_devices', False) and not data.get('confirmed', False):
        return jsonify({
            'error': 'Confirmation required',
            'message': 'Some DHCP devices were not detected. Please confirm you want to proceed.',
            'requires_confirmation': True
        }), 400
    
    try:
        # Write updated configuration to devices.yaml
        import yaml
        
        # Get the devices file path (assuming it's in the working directory)
        devices_file = 'devices.yaml'
        
        # Read existing config to preserve screen_types if they exist
        try:
            with open(devices_file, 'r') as f:
                existing_config = yaml.safe_load(f)
        except FileNotFoundError:
            existing_config = {}
        
        # Update with new device positions
        updated_config = data['config']
        if 'screen_types' in existing_config:
            updated_config['screen_types'] = existing_config['screen_types']
        
        # Write updated configuration
        with open(devices_file, 'w') as f:
            yaml.dump(updated_config, f, default_flow_style=False, indent=2)
        
        # Reload controller with new configuration
        global controller
        from ..models import load_config
        new_config = load_config(devices_file)
        controller.config = new_config
        
        # Restore saved image if available
        restored_image = False
        if last_image_state['image'] is not None:
            try:
                controller.send_image(last_image_state['image'])
                restored_image = True
                logger.info("Restored saved image after applying positioning configuration")
            except Exception as e:
                logger.warning(f"Could not restore saved image: {e}")
        
        message = f'Configuration updated with {len(updated_config["devices"])} devices'
        if restored_image:
            message += '. Previous image restored to displays.'
        
        # Flash success message for homepage display
        flash(message, 'success')
        
        return jsonify({
            'success': True
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to apply configuration: {str(e)}'}), 500

@app.route('/positioning/layout-preview')
def positioning_layout_preview():
    """Generate layout preview for detected positions."""
    if 'detected_config' not in request.args:
        return "No detected configuration", 400
    
    try:
        import json
        detected_config = json.loads(request.args.get('detected_config'))
        
        # Create temporary config from detected positions
        from ..models import Config, Device, Coordinates, DetectedDimensions
        from ..geometry import Point, Dimensions, Rectangle
        import io
        
        devices = []
        for device_data in detected_config.get('devices', []):
            try:
                screen_type_name = device_data['screen_type']
                if screen_type_name not in SCREEN_TYPES:
                    raise ValueError(f"Unknown screen type: {screen_type_name}")
                device = Device(
                    host=device_data['host'],  # hostname stored in host field
                    screen_type=screen_type_name,
                    coordinates=Coordinates(
                        x=device_data['coordinates']['x'],
                        y=device_data['coordinates']['y']
                    ),
                    detected_dimensions=DetectedDimensions(
                        width=device_data['detected_dimensions']['width'],
                        height=device_data['detected_dimensions']['height']
                    ),
                    rotation=device_data.get('rotation', 0)
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
            mimetype='image/png',
            as_attachment=False,
            download_name='detected_layout.png'
        )
        
    except Exception as e:
        logger.error(f"Error generating layout preview: {e}")
        return f"Error generating layout preview: {str(e)}", 500

@app.route('/layout')
def layout():
    """Generate and return the device layout visualization."""
    if not controller:
        return "Controller not initialized", 500
    
    # Generate layout image with last image overlay if available
    img_buffer = io.BytesIO()
    
    if last_image_state['refit_image'] and last_image_state['px_in_unit']:
        controller.config.draw_rectangles_to_buffer(
            img_buffer, 
            last_image_state['refit_image'], 
            last_image_state['px_in_unit']
        )
    else:
        controller.config.draw_rectangles_to_buffer(img_buffer)
    
    img_buffer.seek(0)
    return send_file(img_buffer, mimetype='image/png', as_attachment=False)


@app.route('/layout-data')
def layout_data():
    """Get screen layout data as JSON for canvas operations."""
    try:
        # Get the current image if available
        current_image = None
        image_size = None
        if last_image_state['refit_image'] is not None:
            current_image = "/current-image"  # Endpoint to serve current image
            image_size = {
                'width': last_image_state['refit_image'].size[0],
                'height': last_image_state['refit_image'].size[1]
            }
        
        # Get screen layout information using the new simplified coordinate system  
        screens = []
        if controller and controller.config and controller.config.devices:
            # Create device rectangles in mm (same as new controller logic)
            device_rectangles = {}
            for device in controller.config.devices:
                device_rectangles[device] = Rectangle(
                    start=Point(x=device.coordinates.x, y=device.coordinates.y),
                    dimensions=Dimensions(
                        width=device.detected_dimensions.width,
                        height=device.detected_dimensions.height,
                    )
                )
            
            # Calculate bounding rectangle and get scaling factor
            bounding_rect_mm = Rectangle.bounding_rectangle(device_rectangles.values())
            mm_to_px_ratio = last_image_state.get('px_in_unit')
            
            # If no image has been processed yet, we can't provide pixel coordinates
            if mm_to_px_ratio is None:
                # Return empty screens data when no image is loaded
                screens = []
            else:
                # Convert each device from mm to pixels in scaled image coordinate system
                for device, rect_mm in device_rectangles.items():
                    # Same conversion as the new controller
                    device_rect_px = Rectangle(
                        start=Point(
                            x=int((rect_mm.start.x - bounding_rect_mm.start.x) * mm_to_px_ratio),
                            y=int((rect_mm.start.y - bounding_rect_mm.start.y) * mm_to_px_ratio)
                        ),
                        dimensions=Dimensions(
                            width=int(rect_mm.dimensions.width * mm_to_px_ratio),
                            height=int(rect_mm.dimensions.height * mm_to_px_ratio)
                        )
                    )
                    
                    screen_info = {
                        'hostname': device.host,
                        'screen_type': device.screen_type,
                        'x': device_rect_px.start.x,
                        'y': device_rect_px.start.y,
                        'width': device_rect_px.dimensions.width,
                        'height': device_rect_px.dimensions.height,
                        'rotation': device.rotation
                    }
                    screens.append(screen_info)
        
        return jsonify({
            'current_image': current_image,
            'image_size': image_size,
            'screens': screens,
            'scale_factor': last_image_state.get('px_in_unit', 1.0),
            'use_server_rendering': USE_SERVER_SIDE_RENDERING
        })
        
    except Exception as e:
        logger.error(f"Error getting layout data: {e}")
        return jsonify({
            'current_image': None,
            'image_size': None,
            'screens': [],
            'scale_factor': 1.0,
            'error': str(e)
        })



@app.route('/current-image')
def current_image():
    """Serve the current image thumbnail for the canvas with caching support."""
    try:
        # Get or create thumbnail
        thumbnail = get_or_create_thumbnail()
        if thumbnail is not None:
            # Convert thumbnail to bytes
            img_buffer = io.BytesIO()
            thumbnail.save(img_buffer, format='PNG')
            img_data = img_buffer.getvalue()
        else:
            # Return empty/placeholder image
            placeholder_img = PIL.Image.new('RGB', (400, 300), color='white')
            img_buffer = io.BytesIO()
            placeholder_img.save(img_buffer, format='PNG')
            img_data = img_buffer.getvalue()

        # Calculate MD5 hash of the image data
        md5_hash = hashlib.md5(img_data).hexdigest()
        etag = f'"{md5_hash}"'

        # Check if client has the same version
        client_etag = request.headers.get('If-None-Match')
        if client_etag == etag:
            return '', 304  # Not Modified

        # Create new buffer for sending
        img_buffer = io.BytesIO(img_data)
        response = send_file(img_buffer, mimetype='image/png')

        # Add caching headers
        response.headers['ETag'] = etag
        response.headers['Cache-Control'] = 'private, max-age=0, must-revalidate'
        return response

    except Exception as e:
        logger.error(f"Error serving current image: {e}")
        # Return error placeholder
        error_img = PIL.Image.new('RGB', (400, 300), color='lightgray')
        img_buffer = io.BytesIO()
        error_img.save(img_buffer, format='PNG')
        img_data = img_buffer.getvalue()

        # Hash the error image too
        md5_hash = hashlib.md5(img_data).hexdigest()
        etag = f'"{md5_hash}"'

        img_buffer = io.BytesIO(img_data)
        response = send_file(img_buffer, mimetype='image/png')
        response.headers['ETag'] = etag
        return response


@app.route('/layout-image')
def layout_image():
    """Serve a server-side rendered layout image with screen rectangles."""
    try:
        if not controller or not controller.config or not controller.config.devices:
            return '', 404
            
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
        bounding_rectangle = Rectangle.bounding_rectangle(device_rectangles.values())
        
        # Use the scaled image if available, otherwise create a white background
        if last_image_state['refit_image'] is not None:
            scaled_image = last_image_state['refit_image'].copy()
        else:
            # Create a white background scaled to the bounding rectangle
            scaled_image, _ = controller._scale_image_to_layout(
                PIL.Image.new('RGB', (800, 600), 'white'), 
                bounding_rectangle.dimensions
            )
        
        # Get mm_to_px_ratio scaling factor
        mm_to_px_ratio = last_image_state.get('px_in_unit')
        
        # If no image has been processed, return a simple placeholder
        if mm_to_px_ratio is None:
            mm_to_px_ratio = 1.0  # Default scale for placeholder
        
        # Create visualization by drawing screen rectangles 
        layout_image = create_layout_visualization(
            scaled_image, device_rectangles, mm_to_px_ratio
        )
        
        # Convert to bytes and serve
        img_buffer = io.BytesIO()
        layout_image.save(img_buffer, format='PNG')
        img_buffer.seek(0)
        return send_file(img_buffer, mimetype='image/png')
        
    except Exception as e:
        logger.error(f"Error serving layout image: {e}")
        return '', 500


@app.route('/upload', methods=['POST'])
def upload_image():
    """Handle image upload and send to devices."""
    if 'image' not in request.files:
        flash('No image file provided')
        return redirect(url_for('index'))
    
    file = request.files['image']
    if file.filename == '':
        flash('No file selected')
        return redirect(url_for('index'))
    
    if not allowed_file(file.filename):
        flash('Invalid file type. Please upload an image file.')
        return redirect(url_for('index'))
    
    try:
        # Open and fix EXIF orientation
        image = PIL.Image.open(file.stream)
        image = fix_image_orientation(image)
        
        # Send to devices first
        controller.send_image(image)
        
        # Only save for layout overlay if send was successful
        save_last_image(image)
        
        flash(f'Successfully sent image to {len(controller.config.devices)} devices!')
        return redirect(url_for('index'))
        
    except Exception as e:
        flash(f'Error processing image: {str(e)}')
        return redirect(url_for('index'))

@app.route('/api/upload', methods=['POST'])
def api_upload_image():
    """API endpoint for uploading and displaying images on screens."""
    try:
        # Check if image file is present
        if 'image' not in request.files:
            return jsonify({'error': 'No image file provided'}), 400

        file = request.files['image']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        if not allowed_file(file.filename):
            return jsonify({'error': 'Invalid file type. Please upload an image file.'}), 400

        if not controller:
            return jsonify({'error': 'Controller not initialized'}), 500

        # Open and fix EXIF orientation
        image = PIL.Image.open(file.stream)
        image = fix_image_orientation(image)

        # Send to devices
        controller.send_image(image)

        # Save for layout overlay
        save_last_image(image)

        # Return success response with device info
        response_data = {
            'success': True,
            'message': f'Successfully sent image to {len(controller.config.devices)} devices',
            'devices_updated': len(controller.config.devices),
            'filename': file.filename,
            'image_size': {
                'width': image.size[0],
                'height': image.size[1]
            }
        }

        return jsonify(response_data), 200

    except Exception as e:
        return jsonify({
            'error': 'Failed to process and send image',
            'details': str(e)
        }), 500

@app.route('/devices')
def devices_info():
    """Return device information as JSON."""
    if not controller:
        return jsonify({'error': 'Controller not initialized'}), 500
    
    devices = []
    for device in controller.config.devices:
        devices.append({
            'host': device.host,
            'screen_type': device.screen_type,
            'coordinates': {'x': device.coordinates.x, 'y': device.coordinates.y},
            'rotation': device.rotation,
            'dimensions': {
                'width': device.detected_dimensions.width,
                'height': device.detected_dimensions.height
            }
        })
    
    return jsonify({'devices': devices})

@app.route('/clear', methods=['POST'])
def clear_screens():
    """Clear all device screens."""
    if not controller:
        return jsonify({'error': 'Controller not initialized'}), 500
    
    try:
        controller.clear_devices()
        
        return jsonify({
            'success': True,
            'message': f'Cleared {len(controller.config.devices)} devices'
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to clear screens: {str(e)}'}), 500


@app.route('/restore-image', methods=['POST'])
def restore_last_image():
    """Restore the last saved image from disk."""
    if not controller:
        return jsonify({'error': 'Controller not initialized'}), 500
    
    try:
        # Load the persisted image
        if load_persisted_image():
            # If image was loaded successfully, also send it to devices
            if last_image_state['image'] is not None:
                controller.send_image(last_image_state['image'])
                return jsonify({
                    'success': True,
                    'message': 'Successfully restored and sent last image to devices'
                })
            else:
                return jsonify({'error': 'Image loaded but not available'}), 500
        else:
            return jsonify({'error': 'No saved image found to restore'}), 404
            
    except Exception as e:
        return jsonify({'error': f'Failed to restore image: {str(e)}'}), 500


def get_wallpaper_images():
    """Get list of wallpaper images from wallpapers directory."""
    patterns = ['*.png', '*.jpg', '*.jpeg', '*.gif', '*.bmp', '*.tiff', '*.webp']
    images = []
    config = get_screensaver_config()
    wallpapers_dir = config['gallery']['wallpapers_dir']
    for pattern in patterns:
        images.extend(glob.glob(os.path.join(wallpapers_dir, pattern)))
    return images

def get_reddit_wallpaper():
    """Fetch a random wallpaper from Reddit."""
    import requests
    import random
    from urllib.parse import urlparse

    config = get_screensaver_config()['reddit']
    url = f"https://www.reddit.com/r/{config['subreddit']}/{config['sort']}/.json"
    params = {
        't': config['time_period'],
        'limit': config['limit']
    }

    headers = {
        'User-Agent': 'Tapestry:v1.0 (by /u/tapestry_user)'
    }

    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()

        # Filter posts that have valid image URLs
        image_posts = []
        for post in data['data']['children']:
            post_data = post['data']
            url = post_data.get('url', '')

            # Skip deleted/removed posts or posts without URLs
            if not url or post_data.get('removed_by_category') or post_data.get('is_self'):
                continue

            # Check if it's a direct image URL
            parsed_url = urlparse(url)
            if parsed_url.path.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                image_posts.append({
                    'url': url,
                    'title': post_data.get('title', 'Reddit Wallpaper')
                })
            # Also check for common image hosting sites
            elif any(domain in parsed_url.netloc.lower() for domain in ['i.imgur.com', 'i.redd.it']):
                image_posts.append({
                    'url': url,
                    'title': post_data.get('title', 'Reddit Wallpaper')
                })

        if not image_posts:
            raise Exception("No valid image posts found")

        # Select random image
        selected = random.choice(image_posts)

        # Download the image
        img_response = requests.get(selected['url'], headers=headers, timeout=30)
        img_response.raise_for_status()

        # Open as PIL Image
        from io import BytesIO
        image = PIL.Image.open(BytesIO(img_response.content))
        logger.info(f"Reddit screensaver: displaying '{selected['title']}'")

        return image

    except Exception as e:
        logger.error(f"Error fetching Reddit wallpaper: {str(e)}")
        return None

def screensaver_worker():
    """Background worker that cycles through wallpaper images."""
    stop_event = screensaver_runtime['stop_event']
    first_iteration = True

    while not stop_event.is_set():
        try:
            image = None
            config = get_screensaver_config()

            if config['type'] == 'gallery':
                # Get list of wallpaper images
                images = get_wallpaper_images()
                if not images:
                    logger.warning(f"No wallpaper images found in {config['gallery']['wallpapers_dir']}")
                    stop_event.wait(config['interval'])
                    continue

                # Choose random image
                image_path = random.choice(images)
                logger.info(f"Gallery screensaver: displaying {os.path.basename(image_path)}")

                # Load image
                image = PIL.Image.open(image_path)

            elif config['type'] == 'reddit':
                # Fetch image from Reddit
                image = get_reddit_wallpaper()
                if not image:
                    logger.warning("Failed to fetch Reddit wallpaper, waiting...")
                    stop_event.wait(config['interval'])
                    continue

            if not image:
                logger.warning(f"No image available for screensaver type: {config['type']}")
                stop_event.wait(config['interval'])
                continue
            
            # Send to devices first
            controller.send_image(image)
            
            # Only save for layout overlay if send was successful
            save_last_image(image)
            
        except Exception as e:
            logger.error(f"Screensaver error: {e}")
        
        # Wait for next cycle or stop signal
        # For first iteration, don't wait - show image immediately
        if not first_iteration:
            stop_event.wait(config['interval'])
        first_iteration = False

def start_screensaver_internal():
    """Start the screensaver (internal version for startup)."""
    if not controller:
        raise Exception('Controller not initialized')

    if screensaver_runtime['active']:
        raise Exception('Screensaver already active')

    # Starting screensaver automatically enables it
    settings = get_settings()
    settings.screensaver.enabled = True
    settings.save_to_file()

    config = get_screensaver_config()

    # Validate screensaver type-specific requirements
    image_count = 0
    if config['type'] == 'gallery':
        wallpapers_dir = config['gallery']['wallpapers_dir']
        if not os.path.exists(wallpapers_dir):
            raise Exception(f"Wallpapers directory '{wallpapers_dir}' not found")

        images = get_wallpaper_images()
        if not images:
            raise Exception(f"No wallpaper images found in '{wallpapers_dir}'")
        image_count = len(images)
    elif config['type'] == 'reddit':
        # For Reddit, we'll validate connectivity when we actually try to fetch
        image_count = config['reddit']['limit']

    # Start screensaver thread
    screensaver_runtime['stop_event'] = threading.Event()
    screensaver_runtime['thread'] = threading.Thread(target=screensaver_worker)
    screensaver_runtime['thread'].daemon = True
    screensaver_runtime['active'] = True
    screensaver_runtime['thread'].start()

    return f'Screensaver started with {config["type"]} type'


@app.route('/screensaver/start', methods=['POST'])
def start_screensaver():
    """Start the screensaver."""
    if not controller:
        return jsonify({'error': 'Controller not initialized'}), 500

    if screensaver_runtime['active']:
        return jsonify({'error': 'Screensaver already active'}), 400

    try:
        message = start_screensaver_internal()
        return jsonify({'success': True, 'message': message})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/screensaver/stop', methods=['POST'])
def stop_screensaver():
    """Stop the screensaver."""
    if not screensaver_runtime['active']:
        return jsonify({'error': 'Screensaver not active'}), 400

    try:
        # Stop the screensaver thread
        if screensaver_runtime['stop_event']:
            screensaver_runtime['stop_event'].set()

        if screensaver_runtime['thread'] and screensaver_runtime['thread'].is_alive():
            screensaver_runtime['thread'].join(timeout=2)

        screensaver_runtime['active'] = False
        screensaver_runtime['thread'] = None
        screensaver_runtime['stop_event'] = None

        # Stopping screensaver automatically disables it
        settings = get_settings()
        settings.screensaver.enabled = False
        settings.save_to_file()

        return jsonify({
            'success': True,
            'message': 'Screensaver stopped'
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to stop screensaver: {str(e)}'}), 500

@app.route('/screensaver/status')
def screensaver_status():
    """Get screensaver status."""
    config = get_screensaver_config()
    status = {
        'active': screensaver_runtime['active'],
        'enabled': config['enabled'],
        'type': config['type'],
        'interval': config['interval']
    }

    if config['type'] == 'gallery':
        images = get_wallpaper_images()
        status.update({
            'wallpapers_dir': config['gallery']['wallpapers_dir'],
            'image_count': len(images),
            'has_images': len(images) > 0
        })
    elif config['type'] == 'reddit':
        status.update({
            'wallpapers_dir': f"r/{config['reddit']['subreddit']}",
            'image_count': config['reddit']['limit'],
            'has_images': True  # Assume Reddit is available
        })

    return jsonify(status)

@app.route('/screensaver/wallpaper-dirs')
def get_wallpaper_directories():
    """Get available wallpaper directories."""
    return jsonify({
        'directories': ['wallpapers']
    })

@app.route('/screensaver/config/reddit')
def get_reddit_config():
    """Get Reddit screensaver configuration."""
    settings = get_settings()
    return jsonify(settings.screensaver.reddit.model_dump())

@app.route('/screensaver/config', methods=['POST'])
def update_screensaver_config():
    """Update screensaver configuration."""
    # Handle both form data and JSON data
    if request.content_type and 'application/json' in request.content_type:
        data = request.get_json()
    else:
        data = request.form.to_dict()

    if not data:
        return jsonify({'error': 'No data provided'}), 400

    try:
        settings = get_settings()
        was_active = screensaver_runtime['active']

        # Stop screensaver if active (we'll restart if needed)
        if was_active:
            if screensaver_runtime['stop_event']:
                screensaver_runtime['stop_event'].set()
            if screensaver_runtime['thread'] and screensaver_runtime['thread'].is_alive():
                screensaver_runtime['thread'].join(timeout=2)
            screensaver_runtime['active'] = False

        # Create updated screensaver settings
        current = settings.screensaver

        # Update basic settings
        new_interval = int(data['interval']) if 'interval' in data else current.interval
        new_type = data['type'] if 'type' in data else current.type

        # Update gallery settings
        if 'wallpapers_dir' in data:
            new_gallery = GallerySettings(wallpapers_dir=data['wallpapers_dir'].strip())
        else:
            new_gallery = current.gallery

        # Update reddit settings
        new_reddit_data = {}
        if 'reddit_limit' in data:
            new_reddit_data['limit'] = int(data['reddit_limit'])
        if 'reddit_subreddit' in data:
            new_reddit_data['subreddit'] = data['reddit_subreddit'].strip()

        if new_reddit_data:
            # Merge with current reddit settings
            current_reddit = current.reddit.model_dump()
            current_reddit.update(new_reddit_data)
            new_reddit = RedditSettings(**current_reddit)
        else:
            new_reddit = current.reddit

        # Create new screensaver settings
        settings.screensaver = ScreensaverSettings(
            enabled=current.enabled,
            type=new_type,
            interval=new_interval,
            gallery=new_gallery,
            reddit=new_reddit
        )
        settings.save_to_file()

        # Restart screensaver if it was active
        if was_active:
            screensaver_runtime['stop_event'] = threading.Event()
            screensaver_runtime['thread'] = threading.Thread(target=screensaver_worker)
            screensaver_runtime['thread'].daemon = True
            screensaver_runtime['active'] = True
            screensaver_runtime['thread'].start()

        # Build response config info
        config_info = {
            'type': settings.screensaver.type,
            'interval': settings.screensaver.interval
        }

        if settings.screensaver.type == 'gallery':
            config_info['wallpapers_dir'] = settings.screensaver.gallery.wallpapers_dir
        elif settings.screensaver.type == 'reddit':
            config_info['reddit_limit'] = settings.screensaver.reddit.limit
            config_info['reddit_subreddit'] = settings.screensaver.reddit.subreddit

        return jsonify({
            'success': True,
            'message': 'Screensaver configuration updated successfully',
            'config': config_info,
            'restarted': was_active
        })

    except ValueError as e:
        return jsonify({'error': f'Invalid configuration value: {str(e)}'}), 400
    except Exception as e:
        return jsonify({'error': f'Failed to update configuration: {str(e)}'}), 500

# Global state for flash process
flash_processes = {}

def stream_subprocess_output(process, process_id):
    """Stream subprocess output line by line."""
    try:
        while True:
            output = process.stdout.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                # Store output in process queue
                if process_id in flash_processes:
                    flash_processes[process_id]['output'].put(output.strip())
        
        # Process finished
        if process_id in flash_processes:
            return_code = process.poll()
            flash_processes[process_id]['finished'] = True
            flash_processes[process_id]['return_code'] = return_code
            flash_processes[process_id]['output'].put(f"Process finished with exit code: {return_code}")
    except Exception as e:
        if process_id in flash_processes:
            flash_processes[process_id]['output'].put(f"Error streaming output: {e}")

@app.route('/flash/start', methods=['POST'])
def start_flash():
    """Start the firmware flashing process."""
    data = request.get_json()
    if not data or 'screen_type' not in data:
        return jsonify({'error': 'Screen type is required'}), 400
    
    screen_type = data['screen_type']
    if screen_type not in SCREEN_TYPES:
        return jsonify({'error': f'Invalid screen type: {screen_type}'}), 400
    
    # Check if setup.sh exists
    setup_script = os.path.expanduser('~/node/setup.sh')
    if not os.path.exists(setup_script):
        return jsonify({'error': f'Setup script not found at {setup_script}'}), 404
    
    if not os.access(setup_script, os.X_OK):
        return jsonify({'error': f'Setup script is not executable: {setup_script}'}), 403
    
    try:
        # Generate unique process ID
        import uuid
        process_id = str(uuid.uuid4())
        
        # Start the subprocess
        process = subprocess.Popen(
            [setup_script, screen_type],
            cwd=os.path.expanduser('~/node'),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1
        )
        
        # Initialize process tracking
        output_queue = queue.Queue()
        flash_processes[process_id] = {
            'process': process,
            'output': output_queue,
            'finished': False,
            'return_code': None,
            'screen_type': screen_type
        }
        
        # Start output streaming thread
        output_thread = threading.Thread(
            target=stream_subprocess_output, 
            args=(process, process_id)
        )
        output_thread.daemon = True
        output_thread.start()
        
        return jsonify({
            'success': True,
            'process_id': process_id,
            'message': f'Started flashing {screen_type} firmware'
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to start flash process: {str(e)}'}), 500

@app.route('/flash/output/<process_id>')
def flash_output_stream(process_id):
    """Stream the output of a flash process."""
    if process_id not in flash_processes:
        return jsonify({'error': 'Process not found'}), 404
    
    def generate():
        process_info = flash_processes[process_id]
        output_queue = process_info['output']
        
        while True:
            try:
                # Get output with timeout
                line = output_queue.get(timeout=1.0)
                yield f"data: {line}\n\n"
                
                # Check if process finished
                if process_info['finished'] and output_queue.empty():
                    yield f"event: finished\ndata: {process_info['return_code']}\n\n"
                    break
                    
            except queue.Empty:
                # Send heartbeat to keep connection alive
                if process_info['finished']:
                    yield f"event: finished\ndata: {process_info['return_code']}\n\n"
                    break
                else:
                    yield "data: \n\n"  # Heartbeat
    
    return Response(generate(), 
                   mimetype='text/event-stream',
                   headers={'Cache-Control': 'no-cache', 
                           'Connection': 'keep-alive'})

@app.route('/flash/stop/<process_id>', methods=['POST'])
def stop_flash(process_id):
    """Stop a running flash process."""
    if process_id not in flash_processes:
        return jsonify({'error': 'Process not found'}), 404
    
    try:
        process_info = flash_processes[process_id]
        process = process_info['process']
        
        if process.poll() is None:  # Process is still running
            process.terminate()
            # Wait a bit for graceful termination
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()  # Force kill if it doesn't terminate
        
        # Mark as finished
        process_info['finished'] = True
        process_info['return_code'] = process.returncode
        process_info['output'].put("Process terminated by user")
        
        return jsonify({
            'success': True,
            'message': 'Flash process stopped'
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to stop process: {str(e)}'}), 500

def create_app(devices_file='devices.yaml'):
    """Create Flask app with configuration."""
    global controller
    controller = TapestryController.from_config_file(devices_file)
    return app

def parse_args():
    parser = argparse.ArgumentParser(description="Start Tapestry Web UI")
    parser.add_argument(
        '--devices-file', 
        default='devices.yaml',
        help='YAML file containing device configuration'
    )
    parser.add_argument(
        '--host',
        default='0.0.0.0',
        help='Host to bind to (default: 0.0.0.0)'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=5000,
        help='Port to bind to (default: 5000)'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug mode'
    )
    return parser.parse_args()

def main():
    """Main entry point for web UI."""
    args = parse_args()

    # Set up logging
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format='[%(levelname)s] %(message)s'
    )

    # Initialize settings
    logger.info("Initializing settings...")
    get_settings()

    # Initialize controller
    global controller
    controller = TapestryController.from_config_file(args.devices_file)

    # Auto-start screensaver if enabled in settings
    settings = get_settings()
    if settings.screensaver.enabled:
        logger.info("Screensaver is enabled in settings, starting automatically...")
        try:
            message = start_screensaver_internal()
            logger.info(f"Screensaver started successfully: {message}")
        except Exception as e:
            logger.error(f"Failed to auto-start screensaver: {e}")

    # Start image loading in background thread
    # Automatic image loading on startup has been removed
    # Use the "Restore Last Image" button on the main page instead

    logger.info(f"Starting Tapestry Web UI with {len(controller.config.devices)} devices")
    logger.info(f"Access at http://{args.host}:{args.port}")
    logger.info("Use 'Restore Last Image' button to load previous image")

    app.run(host=args.host, port=args.port, debug=args.debug)

if __name__ == '__main__':
    main()
