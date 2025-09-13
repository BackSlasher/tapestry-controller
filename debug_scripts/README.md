# Debug Scripts

This directory contains useful debugging and testing scripts for the positioning system.

## Scripts

### `generate_synthetic_qr_test.py`
Creates synthetic black and white test images with QR codes to verify OpenCV detection capabilities.

**Purpose**: Test that `cv2.QRCodeDetector` can detect QR codes with correct rotations when properly sized.

**Usage**:
```bash
./generate_synthetic_qr_test.py
```

**Output**: 
- `synthetic_qr_test.png` - Generated test image
- Console output showing detection results

### `validate_positioning.py`
Comprehensive validation script that processes real photos and generates layout diagrams for visual comparison.

**Purpose**: Validate the entire positioning pipeline from photo to final layout.

**Usage**:
```bash
./validate_positioning.py <input_photo> [--output-dir <dir>]
```

**Example**:
```bash
./validate_positioning.py ../debug.jpg --output-dir ./validation_output
```

**Output**:
- `<input_name>_input_photo.jpg` - Copy of input photo
- `<input_name>_detected_layout.png` - Generated layout diagram
- Console output with detection details

## Notes

These scripts were created during development to debug and verify the cv2-only QR positioning system. They proved essential for:

1. **Synthetic testing**: Verifying that OpenCV detection works with properly sized QR codes
2. **Real photo validation**: Comparing physical layouts with detected results
3. **Regression testing**: Ensuring changes don't break existing functionality

The synthetic test script was particularly valuable for proving that detection failures in real photos were due to lighting/quality issues rather than algorithmic problems.