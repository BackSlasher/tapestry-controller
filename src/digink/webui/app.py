#!/usr/bin/env python3
import os
import io
import argparse
import time
import random
import glob
import threading
import subprocess
import queue
from flask import Flask, render_template, request, jsonify, send_file, flash, redirect, url_for, Response
from werkzeug.utils import secure_filename
import PIL.Image
from PIL import ExifTags
from ..controller import DiginkController
from ..models import load_config
from ..screen_types import SCREEN_TYPES

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
        print(f"Warning: Could not fix image orientation: {e}")
        # Return original image if EXIF processing fails
        pass
    
    return image

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

@app.route('/flash')
def flash_firmware():
    """Flash firmware page."""
    return render_template('flash.html')

@app.route('/positioning')
def positioning():
    """QR-based positioning page."""
    return render_template('positioning.html')

@app.route('/positioning/qr-mode', methods=['POST'])
def start_qr_positioning():
    """Start QR positioning mode - display QR codes on all screens."""
    if not controller:
        return jsonify({'error': 'Controller not initialized'}), 500
    
    try:
        from ..positioning import generate_positioning_qr_image
        
        threads = []
        errors = []
        
        for device in controller.config.devices:
            try:
                # Get device info to determine actual screen type
                from ..device import info
                device_info = info(device.host)
                screen_type_name = device_info.screen_model
                
                if screen_type_name not in SCREEN_TYPES:
                    errors.append(f"Unknown screen model '{screen_type_name}' for device {device.host}")
                    continue
                
                qr_image = generate_positioning_qr_image(device.host, screen_type_name)
                
                # Send QR image to device
                from ..device import draw
                t = threading.Thread(target=draw, args=(device.host, qr_image, True, 0))  # No rotation for QR positioning
                t.daemon = True
                t.start()
                threads.append(t)
                
            except Exception as e:
                errors.append(f"Error generating QR for {device.host}: {str(e)}")
        
        # Wait for all images to be sent
        for t in threads:
            t.join()
        
        if errors:
            return jsonify({
                'success': True,
                'message': f'QR codes sent to {len(threads)} devices',
                'warnings': errors
            })
        else:
            return jsonify({
                'success': True,
                'message': f'QR codes sent to {len(threads)} devices'
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
        from ..positioning import detect_qr_positions, calculate_physical_positions, generate_updated_config
        
        # Open image and fix EXIF orientation
        image = PIL.Image.open(file.stream)
        corrected_image = fix_image_orientation(image)
        
        # Detect QR codes directly from PIL image
        position_data = detect_qr_positions(corrected_image)
        
        if not position_data:
            return jsonify({'error': 'No QR codes detected in the photo'}), 400
        
        # Calculate physical positions
        physical_positions = calculate_physical_positions(position_data, controller.config)
        
        if not physical_positions:
            return jsonify({'error': 'Could not calculate physical positions'}), 400
        
        # Generate updated configuration
        updated_config = generate_updated_config(controller.config, physical_positions)
        
        # Convert config to YAML for preview
        import yaml
        yaml_preview = yaml.dump(updated_config, default_flow_style=False, indent=2)
        
        return jsonify({
            'success': True,
            'message': f'Detected {len(position_data)} screens',
            'detected_devices': list(physical_positions.keys()),
            'positions': physical_positions,
            'config': updated_config,
            'yaml_preview': yaml_preview
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to analyze photo: {str(e)}'}), 500

@app.route('/positioning/apply', methods=['POST'])
def apply_positioning_config():
    """Apply the detected positioning configuration."""
    data = request.get_json()
    if not data or 'config' not in data:
        return jsonify({'error': 'No configuration provided'}), 400
    
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
        
        return jsonify({
            'success': True,
            'message': f'Configuration updated with {len(updated_config["devices"])} devices'
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to apply configuration: {str(e)}'}), 500

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