"""
Integration test for QR positioning system using real test photo.
"""

import pytest
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from digink.positioning import detect_qr_positions, calculate_physical_positions
from digink.models import Config
from PIL import Image


class TestPositioningIntegration:
    """Integration tests for QR positioning using real test photos."""
    
    @pytest.fixture
    def test_photo_path(self):
        """Path to the test positioning photo."""
        return Path(__file__).parent / "fixtures" / "positioning_test_photo.png"
    
    @pytest.fixture
    def expected_positions(self):
        """Expected positioning results from the test photo."""
        return {
            "10.42.0.98": {
                "position": (151, 243),
                "rotation": -157.8,
                "screen_type": "ED060XC3"
            },
            "10.42.0.166": {
                "position": (23, 269), 
                "rotation": 109.9,
                "screen_type": "ED060XC3"
            },
            "10.42.0.154": {
                "position": (20, 20),
                "rotation": -168.4,
                "screen_type": "ED097TC2"
            }
        }
    
    def test_qr_detection(self, test_photo_path):
        """Test that QR codes are correctly detected from the photo."""
        assert test_photo_path.exists(), f"Test photo not found: {test_photo_path}"
        
        # Load image as PIL Image object
        image = Image.open(test_photo_path)
        qr_data = detect_qr_positions(image)
        
        # Should detect exactly 3 QR codes
        assert len(qr_data) == 3, f"Expected 3 QR codes, found {len(qr_data)}"
        
        # Check that all expected devices are detected
        detected_ips = {qr.hostname for qr in qr_data}
        expected_ips = {"10.42.0.98", "10.42.0.166", "10.42.0.154"}
        assert detected_ips == expected_ips, f"Expected IPs {expected_ips}, got {detected_ips}"
        
        # Verify screen types are correct
        for qr in qr_data:
            if qr.hostname in ["10.42.0.98", "10.42.0.166"]:
                assert qr.screen_type == "ED060XC3", f"Wrong screen type for {qr.hostname}"
            elif qr.hostname == "10.42.0.154":
                assert qr.screen_type == "ED097TC2", f"Wrong screen type for {qr.hostname}"
    
    def test_position_calculation(self, test_photo_path, expected_positions):
        """Test that physical positions are calculated correctly."""
        image = Image.open(test_photo_path)
        qr_data = detect_qr_positions(image)
        empty_config = Config(devices=[])
        positions = calculate_physical_positions(qr_data, empty_config)
        
        # Should have positions for all 3 devices
        assert len(positions) == 3, f"Expected 3 positions, got {len(positions)}"
        
        # Check positioning accuracy (allow small tolerance for image processing variations)
        position_tolerance = 2  # pixels
        rotation_tolerance = 1.0  # degrees
        
        for ip, expected in expected_positions.items():
            assert ip in positions, f"Missing position for device {ip}"
            
            actual_pos = positions[ip]
            expected_x, expected_y = expected["position"]
            
            # Check position accuracy
            pos_diff_x = abs(actual_pos["x"] - expected_x)
            pos_diff_y = abs(actual_pos["y"] - expected_y)
            
            assert pos_diff_x <= position_tolerance, \
                f"X position for {ip} off by {pos_diff_x}px (expected {expected_x}, got {actual_pos['x']})"
            assert pos_diff_y <= position_tolerance, \
                f"Y position for {ip} off by {pos_diff_y}px (expected {expected_y}, got {actual_pos['y']})"
            
            # Check rotation accuracy
            rotation_diff = abs(actual_pos["rotation"] - expected["rotation"])
            assert rotation_diff <= rotation_tolerance, \
                f"Rotation for {ip} off by {rotation_diff}° (expected {expected['rotation']}, got {actual_pos['rotation']})"
            
            # Check screen type
            assert actual_pos["screen_type"] == expected["screen_type"], \
                f"Wrong screen type for {ip}: expected {expected['screen_type']}, got {actual_pos['screen_type']}"
    
    def test_positioning_consistency(self, test_photo_path):
        """Test that positioning results are consistent across multiple runs."""
        # Run positioning multiple times
        results = []
        image = Image.open(test_photo_path)
        for _ in range(3):
            qr_data = detect_qr_positions(image)
            empty_config = Config(devices=[])
            positions = calculate_physical_positions(qr_data, empty_config)
            results.append(positions)
        
        # All runs should produce identical results
        first_result = results[0]
        for i, result in enumerate(results[1:], 1):
            assert result.keys() == first_result.keys(), f"Run {i+1} detected different devices"
            
            for ip in first_result.keys():
                # Positions should be identical (or very close due to floating point)
                x_diff = abs(result[ip]["x"] - first_result[ip]["x"])
                y_diff = abs(result[ip]["y"] - first_result[ip]["y"])
                rot_diff = abs(result[ip]["rotation"] - first_result[ip]["rotation"])
                
                assert x_diff < 0.1, f"Inconsistent X position for {ip} between runs"
                assert y_diff < 0.1, f"Inconsistent Y position for {ip} between runs"  
                assert rot_diff < 0.1, f"Inconsistent rotation for {ip} between runs"
    
    def test_layout_generation(self, test_photo_path):
        """Test that layout diagrams can be generated from positioning results."""
        from digink.models import Config, Device, Coordinates
        from digink.screen_types import SCREEN_TYPES
        import tempfile
        
        image = Image.open(test_photo_path)
        qr_data = detect_qr_positions(image)
        empty_config = Config(devices=[])
        positions = calculate_physical_positions(qr_data, empty_config)
        
        # Manually create devices from positioning results for testing
        devices = []
        for hostname, pos in positions.items():
            screen_type = SCREEN_TYPES[pos["screen_type"]]
            device = Device(
                host=hostname,
                screen_type=screen_type,
                coordinates=Coordinates(x=pos["x"], y=pos["y"]),
                rotation=pos["rotation"]
            )
            devices.append(device)
        
        config = Config(devices=devices)
        assert len(config.devices) == 3, "Config should have 3 devices"
        
        # Should be able to generate layout image
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
            try:
                config.draw_rectangles(temp_file.name)
                assert os.path.exists(temp_file.name), "Layout image should be created"
                assert os.path.getsize(temp_file.name) > 1000, "Layout image should have content"
            finally:
                if os.path.exists(temp_file.name):
                    os.unlink(temp_file.name)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])