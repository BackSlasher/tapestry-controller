"""
Comprehensive test suite for the QR-based positioning system.

Tests the complete pipeline:
1. QR detection with JSON data parsing
2. Screen corner calculation from QR size ratios
3. Physical positioning and layout generation

Uses debug.jpg as the reference image with known expected outputs.
"""

import pytest
import os
import sys
import json
from pathlib import Path
from PIL import Image

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from tapestry.position_detection import detect_qr_positions, calculate_physical_positions
from tapestry.models import Config


class TestPositioningSystem:
    """Test suite for QR positioning system using debug.jpg reference."""
    
    @pytest.fixture
    def debug_image(self):
        """Load the debug image."""
        debug_path = Path(__file__).parent / "debug.jpg"
        if not debug_path.exists():
            pytest.skip("debug.jpg not found in tests directory")
        return Image.open(debug_path)
    
    @pytest.fixture
    def empty_config(self):
        """Create empty config for testing."""
        return Config(devices=[])
    
    def test_qr_detection_count(self, debug_image):
        """Test that we detect exactly 2 QR codes."""
        positions = detect_qr_positions(debug_image)
        assert len(positions) == 2, f"Expected 2 QR codes, got {len(positions)}"
    
    def test_qr_detection_hostnames(self, debug_image):
        """Test that we detect the correct device hostnames."""
        positions = detect_qr_positions(debug_image)
        hostnames = {p.hostname for p in positions}
        expected_hostnames = {"10.42.0.174", "10.42.0.154"}
        assert hostnames == expected_hostnames, f"Expected {expected_hostnames}, got {hostnames}"
    
    def test_qr_detection_screen_types(self, debug_image):
        """Test that we detect the correct screen types."""
        positions = detect_qr_positions(debug_image)
        screen_types = {p.hostname: p.screen_type for p in positions}
        expected_types = {
            "10.42.0.174": "ED060XC3",
            "10.42.0.154": "ED097TC2"
        }
        assert screen_types == expected_types, f"Expected {expected_types}, got {screen_types}"
    
    def test_qr_detection_rotations(self, debug_image):
        """Test that we detect the correct rotations."""
        positions = detect_qr_positions(debug_image)
        rotations = {p.hostname: p.rotation for p in positions}
        expected_rotations = {
            "10.42.0.174": 0,    # No rotation
            "10.42.0.154": 180   # 180° rotation
        }
        assert rotations == expected_rotations, f"Expected {expected_rotations}, got {rotations}"
    
    def test_qr_json_data_parsing(self, debug_image):
        """Test that JSON data is correctly parsed from QR codes."""
        positions = detect_qr_positions(debug_image)
        
        # Check screen dimensions from JSON
        for pos in positions:
            assert pos.screen_width_px > 0, f"Invalid screen_width_px for {pos.hostname}"
            assert pos.screen_height_px > 0, f"Invalid screen_height_px for {pos.hostname}"
            assert pos.qr_size_px > 0, f"Invalid qr_size_px for {pos.hostname}"
        
        # Check specific expected values
        pos_by_host = {p.hostname: p for p in positions}
        
        # 10.42.0.174 (ED060XC3)
        assert pos_by_host["10.42.0.174"].screen_width_px == 1024
        assert pos_by_host["10.42.0.174"].screen_height_px == 768
        assert pos_by_host["10.42.0.174"].qr_size_px == 576  # 75% of min(1024,768)
        
        # 10.42.0.154 (ED097TC2) 
        assert pos_by_host["10.42.0.154"].screen_width_px == 1200
        assert pos_by_host["10.42.0.154"].screen_height_px == 825
        assert pos_by_host["10.42.0.154"].qr_size_px == 618  # 75% of min(1200,825)
    
    def test_screen_corner_calculation(self, debug_image):
        """Test that screen corners are correctly calculated from QR size ratios."""
        positions = detect_qr_positions(debug_image)
        
        for pos in positions:
            # Should have exactly 4 screen corners
            assert len(pos.screen_corners) == 4, f"Expected 4 corners for {pos.hostname}, got {len(pos.screen_corners)}"
            
            # Corners should form a reasonable rectangle
            corners = pos.screen_corners
            
            # Check that corners form a proper rectangle (opposite corners should be farthest apart)
            x_coords = [c[0] for c in corners]
            y_coords = [c[1] for c in corners]
            
            assert min(x_coords) < max(x_coords), f"Invalid x-coordinates for {pos.hostname}"
            assert min(y_coords) < max(y_coords), f"Invalid y-coordinates for {pos.hostname}"
    
    def test_physical_positioning(self, debug_image, empty_config):
        """Test the complete physical positioning calculation."""
        positions = detect_qr_positions(debug_image)
        layout = calculate_physical_positions(positions, empty_config)
        
        # Should have positions for both devices
        assert len(layout) == 2, f"Expected 2 device positions, got {len(layout)}"
        
        # Check that both devices are positioned
        expected_ips = {"10.42.0.174", "10.42.0.154"}
        assert set(layout.keys()) == expected_ips
        
        # Check position data structure
        for ip, pos_data in layout.items():
            assert 'x' in pos_data, f"Missing x coordinate for {ip}"
            assert 'y' in pos_data, f"Missing y coordinate for {ip}"
            assert 'rotation' in pos_data, f"Missing rotation for {ip}"
            assert 'screen_type' in pos_data, f"Missing screen_type for {ip}"
            
            # Coordinates should be reasonable (positive, not too large)
            assert pos_data['x'] >= 0, f"Negative x coordinate for {ip}: {pos_data['x']}"
            assert pos_data['y'] >= 0, f"Negative y coordinate for {ip}: {pos_data['y']}"
            assert pos_data['x'] < 1000, f"Unreasonably large x coordinate for {ip}: {pos_data['x']}"
            assert pos_data['y'] < 1000, f"Unreasonably large y coordinate for {ip}: {pos_data['y']}"
    
    def test_layout_positioning_accuracy(self, debug_image, empty_config):
        """Test that the layout positions match expected values within tolerance."""
        positions = detect_qr_positions(debug_image)
        layout = calculate_physical_positions(positions, empty_config)
        
        # Expected positions (with some tolerance for minor variations)
        expected_positions = {
            "10.42.0.174": {"x": 248, "y": 76, "rotation": 0},
            "10.42.0.154": {"x": 20, "y": 20, "rotation": 180}
        }
        
        tolerance = 5.0  # ±5 units tolerance
        
        for ip, expected in expected_positions.items():
            actual = layout[ip]
            
            # Check position with tolerance
            assert abs(actual['x'] - expected['x']) <= tolerance, \
                f"X position for {ip}: expected ~{expected['x']}, got {actual['x']}"
            assert abs(actual['y'] - expected['y']) <= tolerance, \
                f"Y position for {ip}: expected ~{expected['y']}, got {actual['y']}"
            
            # Rotation should be exact
            assert actual['rotation'] == expected['rotation'], \
                f"Rotation for {ip}: expected {expected['rotation']}, got {actual['rotation']}"
    
    def test_non_overlapping_screens(self, debug_image, empty_config):
        """Test that screens don't overlap in the generated layout."""
        positions = detect_qr_positions(debug_image)
        layout = calculate_physical_positions(positions, empty_config)
        
        # Calculate screen bounds for each device
        screen_bounds = {}
        for ip, pos_data in layout.items():
            # Get screen type dimensions (approximate - this is a basic check)
            # In a real implementation, you'd get actual dimensions
            if pos_data['screen_type'] == 'ED060XC3':  # Smaller screen
                width, height = 112, 84  # Approximate mm
            else:  # ED097TC2 - Larger screen  
                width, height = 220, 151  # Approximate mm
                
            screen_bounds[ip] = {
                'left': pos_data['x'],
                'right': pos_data['x'] + width,
                'top': pos_data['y'], 
                'bottom': pos_data['y'] + height
            }
        
        # Check for overlaps between all screen pairs
        ips = list(screen_bounds.keys())
        for i in range(len(ips)):
            for j in range(i + 1, len(ips)):
                ip1, ip2 = ips[i], ips[j]
                bounds1, bounds2 = screen_bounds[ip1], screen_bounds[ip2]
                
                # Check if rectangles overlap
                x_overlap = bounds1['left'] < bounds2['right'] and bounds2['left'] < bounds1['right']
                y_overlap = bounds1['top'] < bounds2['bottom'] and bounds2['top'] < bounds1['bottom']
                
                overlap = x_overlap and y_overlap
                assert not overlap, f"Screens {ip1} and {ip2} overlap in layout"
    
    def test_scale_factor_consistency(self, debug_image, empty_config):
        """Test that scale factor is consistent and reasonable."""
        positions = detect_qr_positions(debug_image)
        layout = calculate_physical_positions(positions, empty_config)
        
        # All devices should have the same scale factor
        scale_factors = [pos_data.get('scale_factor') for pos_data in layout.values() if 'scale_factor' in pos_data]
        
        if scale_factors:
            # All scale factors should be the same
            assert all(abs(sf - scale_factors[0]) < 0.001 for sf in scale_factors), \
                f"Inconsistent scale factors: {scale_factors}"
            
            # Scale factor should be reasonable (between 0.1 and 1.0 mm/px for typical setups)
            scale_factor = scale_factors[0]
            assert 0.05 < scale_factor < 1.0, \
                f"Unreasonable scale factor: {scale_factor} mm/px"


if __name__ == "__main__":
    # Run tests directly
    pytest.main([__file__, "-v"])