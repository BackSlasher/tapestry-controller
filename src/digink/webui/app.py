#!/usr/bin/env python3
import os
import io
import argparse
import time
import random
import glob
import threading
from flask import Flask, render_template, request, jsonify, send_file, flash, redirect, url_for
from werkzeug.utils import secure_filename
import PIL.Image
from ..controller import DiginkController
from ..models import load_config

app = Flask(__name__)
app.config['SECRET_KEY'] = 'digink-webui-secret-key'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Global controller instance
controller = None

# Screensaver state
screensaver_state = {
    'active': False,
    'thread': None,
    'stop_event': None,
    'wallpapers_dir': 'wallpapers',
    'interval': 60  # seconds
}

# Last image state
last_image_state = {
    'image': None,  # PIL Image object
    'refit_image': None,  # Processed/resized image
    'px_in_unit': None,  # Scaling factor
}

def allowed_file(filename):
    """Check if uploaded file has allowed extension."""
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'tiff'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_last_image(image):
    """Save the last sent image for layout overlay."""
    from ..geometry import Point, Dimensions, Rectangle
    from ..image_utils import image_refit
    
    # Calculate device rectangles and bounding rectangle (same as controller does)
    device_rectangles = {}
    for device in controller.config.devices:
        start = Point(x=device.coordinates.x, y=device.coordinates.y)
        dimensions = Dimensions(
            width=device.screen_type.total_dimensions().width,
            height=device.screen_type.total_dimensions().height,
        )
        device_rectangles[device] = Rectangle(
            start=start,
            dimensions=dimensions,
        )
    
    # Refit image to complete rectangle (same as controller does)
    bounding_rectangle = Rectangle.bounding_rectangle(device_rectangles.values())
    refit_result = image_refit(image, bounding_rectangle.dimensions)
    
    # Save to global state
    last_image_state['image'] = image.copy()
    last_image_state['refit_image'] = refit_result.image.copy()
    last_image_state['px_in_unit'] = refit_result.px_in_unit

@app.route('/')
def index():
    """Main page showing layout and upload form."""
    device_count = len(controller.config.devices) if controller else 0
    return render_template('index.html', device_count=device_count)

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
        # Open and process the image
        image = PIL.Image.open(file.stream)
        
        # Send to devices first
        controller.send_image(image)
        
        # Only save for layout overlay if send was successful
        save_last_image(image)
        
        flash(f'Successfully sent image to {len(controller.config.devices)} devices!')
        return redirect(url_for('index'))
        
    except Exception as e:
        flash(f'Error processing image: {str(e)}')
        return redirect(url_for('index'))

@app.route('/devices')
def devices_info():
    """Return device information as JSON."""
    if not controller:
        return jsonify({'error': 'Controller not initialized'}), 500
    
    devices = []
    for device in controller.config.devices:
        devices.append({
            'host': device.host,
            'screen_type': device.screen_type.__class__.__name__,
            'coordinates': {'x': device.coordinates.x, 'y': device.coordinates.y},
            'dimensions': {
                'width': device.screen_type.total_dimensions().width,
                'height': device.screen_type.total_dimensions().height
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

def get_wallpaper_images():
    """Get list of wallpaper images from wallpapers directory."""
    patterns = ['*.png', '*.jpg', '*.jpeg', '*.gif', '*.bmp', '*.tiff', '*.webp']
    images = []
    for pattern in patterns:
        images.extend(glob.glob(os.path.join(screensaver_state['wallpapers_dir'], pattern)))
    return images

def screensaver_worker():
    """Background worker that cycles through wallpaper images."""
    stop_event = screensaver_state['stop_event']
    first_iteration = True
    
    while not stop_event.is_set():
        try:
            # Get list of wallpaper images
            images = get_wallpaper_images()
            if not images:
                print("No wallpaper images found in", screensaver_state['wallpapers_dir'])
                stop_event.wait(screensaver_state['interval'])
                continue
            
            # Choose random image
            image_path = random.choice(images)
            print(f"Screensaver: displaying {os.path.basename(image_path)}")
            
            # Load and send image
            image = PIL.Image.open(image_path)
            
            # Send to devices first
            controller.send_image(image)
            
            # Only save for layout overlay if send was successful
            save_last_image(image)
            
        except Exception as e:
            print(f"Screensaver error: {e}")
        
        # Wait for next cycle or stop signal
        # For first iteration, don't wait - show image immediately
        if not first_iteration:
            stop_event.wait(screensaver_state['interval'])
        first_iteration = False

@app.route('/screensaver/start', methods=['POST'])
def start_screensaver():
    """Start the screensaver."""
    if not controller:
        return jsonify({'error': 'Controller not initialized'}), 500
    
    if screensaver_state['active']:
        return jsonify({'error': 'Screensaver already active'}), 400
    
    # Check if wallpapers directory exists and has images
    if not os.path.exists(screensaver_state['wallpapers_dir']):
        return jsonify({'error': f"Wallpapers directory '{screensaver_state['wallpapers_dir']}' not found"}), 400
    
    images = get_wallpaper_images()
    if not images:
        return jsonify({'error': f"No wallpaper images found in '{screensaver_state['wallpapers_dir']}'"}), 400
    
    try:
        # Start screensaver thread
        screensaver_state['stop_event'] = threading.Event()
        screensaver_state['thread'] = threading.Thread(target=screensaver_worker)
        screensaver_state['thread'].daemon = True
        screensaver_state['active'] = True
        screensaver_state['thread'].start()
        
        return jsonify({
            'success': True,
            'message': f'Screensaver started with {len(images)} wallpapers',
            'image_count': len(images)
        })
        
    except Exception as e:
        screensaver_state['active'] = False
        return jsonify({'error': f'Failed to start screensaver: {str(e)}'}), 500

@app.route('/screensaver/stop', methods=['POST'])
def stop_screensaver():
    """Stop the screensaver."""
    if not screensaver_state['active']:
        return jsonify({'error': 'Screensaver not active'}), 400
    
    try:
        # Stop the screensaver thread
        if screensaver_state['stop_event']:
            screensaver_state['stop_event'].set()
        
        if screensaver_state['thread'] and screensaver_state['thread'].is_alive():
            screensaver_state['thread'].join(timeout=2)
        
        screensaver_state['active'] = False
        screensaver_state['thread'] = None
        screensaver_state['stop_event'] = None
        
        return jsonify({
            'success': True,
            'message': 'Screensaver stopped'
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to stop screensaver: {str(e)}'}), 500

@app.route('/screensaver/status')
def screensaver_status():
    """Get screensaver status."""
    images = get_wallpaper_images()
    
    return jsonify({
        'active': screensaver_state['active'],
        'interval': screensaver_state['interval'],
        'wallpapers_dir': screensaver_state['wallpapers_dir'],
        'image_count': len(images),
        'has_images': len(images) > 0
    })

@app.route('/screensaver/config', methods=['POST'])
def update_screensaver_config():
    """Update screensaver configuration."""
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    # Validate interval
    if 'interval' in data:
        try:
            interval = int(data['interval'])
            if interval < 5 or interval > 3600:  # 5 seconds to 1 hour
                return jsonify({'error': 'Interval must be between 5 and 3600 seconds'}), 400
            
            # If screensaver is currently active, we need to restart it with new interval
            was_active = screensaver_state['active']
            if was_active:
                # Stop current screensaver
                if screensaver_state['stop_event']:
                    screensaver_state['stop_event'].set()
                if screensaver_state['thread'] and screensaver_state['thread'].is_alive():
                    screensaver_state['thread'].join(timeout=2)
                screensaver_state['active'] = False
            
            # Update interval
            screensaver_state['interval'] = interval
            
            # Restart screensaver if it was active
            if was_active:
                screensaver_state['stop_event'] = threading.Event()
                screensaver_state['thread'] = threading.Thread(target=screensaver_worker)
                screensaver_state['thread'].daemon = True
                screensaver_state['active'] = True
                screensaver_state['thread'].start()
            
            return jsonify({
                'success': True,
                'message': f'Screensaver interval updated to {interval} seconds',
                'interval': interval,
                'restarted': was_active
            })
            
        except ValueError:
            return jsonify({'error': 'Invalid interval value'}), 400
    
    return jsonify({'error': 'No valid configuration provided'}), 400

def create_app(devices_file='devices.yaml'):
    """Create Flask app with configuration."""
    global controller
    controller = DiginkController.from_config_file(devices_file)
    return app

def parse_args():
    parser = argparse.ArgumentParser(description="Start Digink Web UI")
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
    
    # Initialize controller
    global controller
    controller = DiginkController.from_config_file(args.devices_file)
    
    print(f"Starting Digink Web UI with {len(controller.config.devices)} devices")
    print(f"Access at http://{args.host}:{args.port}")
    
    app.run(host=args.host, port=args.port, debug=args.debug)

if __name__ == '__main__':
    main()