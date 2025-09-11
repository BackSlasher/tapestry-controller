#!/usr/bin/env python3
"""
Simple test runner for QR positioning system.
Run this script to test the synthetic photo generation and recognition pipeline.
"""

import sys
import os

# Add src to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from digink.test_positioning import run_all_positioning_tests

if __name__ == "__main__":
    print("QR Positioning Recognition Test Suite")
    print("=====================================")
    print()
    
    success = run_all_positioning_tests()
    
    if success:
        print("\n🎉 All tests passed!")
        sys.exit(0)
    else:
        print("\n❌ Some tests failed.")
        sys.exit(1)