# Digink - Distributed E-ink Display Controller

A Python package for managing distributed e-ink displays. Splits large images across multiple e-paper devices arranged in a configurable layout.

## Features

- Configure multiple e-ink devices with different screen types and positions
- Automatically resize and crop images to fit device layout
- Send image portions to devices in parallel via HTTP
- Support for various e-paper display models (ED060XC3, ED097TC2, etc.)
- Debug output for layout visualization

## Installation

```bash
# Install the package
make install

# Install with development dependencies
make install-dev
```

## Usage

### Command Line

```bash
# Send an image to all configured devices
digink path/to/image.png

# Specify custom device configuration file
digink path/to/image.png --devices-file my-devices.yaml

# Generate debug output showing layout and resized image
digink path/to/image.png --debug-output-dir debug/
```

### Python API

```python
from digink import DiginkController
import PIL.Image

# Load controller from config file
controller = DiginkController.from_config_file("devices.yaml")

# Send image to all devices
image = PIL.Image.open("image.png")
controller.send_image(image)
```

## Configuration

Create a `devices.yaml` file defining your display layout:

```yaml
devices:
  - host: 192.168.1.100
    screen_type: ED097TC2
    coordinates:
      x: 0
      y: 0
  - host: 192.168.1.101  
    screen_type: ED060XC3
    coordinates:
      x: 210
      y: 50

screen_types:
  ED097TC2:
    active_area:
      height: 139.425
      width: 202.8
    bezel:
      top: 4.0
      bottom: 12.0
      left: 4.0
      right: 12.0
  ED060XC3:
    active_area:
      height: 90.58
      width: 122.37
    bezel:
      left: 0.2
      right: 1.4
      top: 0.5
      bottom: 0.5
```

## Development

```bash
# Run tests
make test

# Format code
make lint

# Type checking
make type-check

# Clean build artifacts
make clean
```

## Project Structure

```
src/digink/
├── __init__.py          # Package initialization
├── cli.py              # Command-line interface
├── controller.py       # Main controller class
├── device.py          # Device communication
├── models.py          # Configuration models
├── geometry.py        # Geometric primitives
└── image_utils.py     # Image processing utilities
```