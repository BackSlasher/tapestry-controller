#!/usr/bin/env python3
import os
import io
import argparse
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

def allowed_file(filename):
    """Check if uploaded file has allowed extension."""
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'tiff'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

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
    
    # Create layout image in memory
    device_rectangles = controller.config.to_rectangles()
    from ..geometry import Rectangle
    bounding_rectangle = Rectangle.bounding_rectangle(device_rectangles.values())
    
    # Generate layout image
    img_buffer = io.BytesIO()
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
        
        # Send to devices
        controller.send_image(image)
        
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
        default='127.0.0.1',
        help='Host to bind to (default: 127.0.0.1)'
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