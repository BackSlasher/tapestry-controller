"""
Perspective correction using rectangular screen constraints.

Uses the known rectangular nature of screens to detect and correct perspective distortion.
"""

import math
import numpy as np
from typing import List, Tuple, NamedTuple
import cv2

from .position_detection import QRPositionData


class CorrectedQRData(NamedTuple):
    """QR position data with perspective correction applied."""
    original: QRPositionData
    corrected_center: Tuple[float, float]
    corrected_corners: List[Tuple[float, float]]
    corrected_screen_corners: List[Tuple[float, float]]
    rectangularity_score: float


def calculate_rectangularity_score(corners: List[Tuple[float, float]]) -> float:
    """
    Calculate how rectangular a set of 4 corners is.
    Returns a score where 1.0 = perfect rectangle, lower = more distorted.
    """
    if len(corners) != 4:
        return 0.0

    # Convert to numpy array for easier math
    pts = np.array(corners, dtype=np.float32)

    # Calculate all 4 side lengths
    side_lengths = []
    for i in range(4):
        p1 = pts[i]
        p2 = pts[(i + 1) % 4]
        length = np.linalg.norm(p2 - p1)
        side_lengths.append(length)

    # Calculate all 4 angles
    angles = []
    for i in range(4):
        p1 = pts[(i - 1) % 4]
        p2 = pts[i]
        p3 = pts[(i + 1) % 4]

        # Vectors from p2 to p1 and p2 to p3
        v1 = p1 - p2
        v2 = p3 - p2

        # Calculate angle between vectors
        cos_angle = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))
        cos_angle = np.clip(cos_angle, -1.0, 1.0)  # Handle numerical errors
        angle = math.acos(cos_angle)
        angles.append(angle)

    # For a perfect rectangle:
    # - Opposite sides should be equal
    # - All angles should be 90 degrees (π/2 radians)

    # Score based on side length consistency
    opposite_pairs = [(side_lengths[0], side_lengths[2]), (side_lengths[1], side_lengths[3])]
    side_score = 1.0
    for pair in opposite_pairs:
        ratio = min(pair) / max(pair) if max(pair) > 0 else 0
        side_score *= ratio

    # Score based on angle consistency (should all be π/2)
    angle_score = 1.0
    target_angle = math.pi / 2
    for angle in angles:
        angle_error = abs(angle - target_angle) / target_angle
        angle_factor = max(0, 1.0 - angle_error)
        angle_score *= angle_factor

    # Combined score
    rectangularity = side_score * angle_score
    return rectangularity


def calculate_ideal_rectangle(center: Tuple[float, float],
                            width: float,
                            height: float,
                            rotation: float = 0.0) -> List[Tuple[float, float]]:
    """
    Calculate the corners of an ideal rectangle given center, dimensions, and rotation.

    Args:
        center: (x, y) center point
        width: Rectangle width
        height: Rectangle height
        rotation: Rotation in radians (0 = no rotation)

    Returns:
        List of 4 corner points as (x, y) tuples
    """
    cx, cy = center

    # Half dimensions
    hw = width / 2
    hh = height / 2

    # Corner offsets from center (before rotation)
    corners_offset = [
        (-hw, -hh),  # top-left
        (hw, -hh),   # top-right
        (hw, hh),    # bottom-right
        (-hw, hh)    # bottom-left
    ]

    # Apply rotation and translate to center
    cos_r = math.cos(rotation)
    sin_r = math.sin(rotation)

    corners = []
    for dx, dy in corners_offset:
        # Rotate
        rx = dx * cos_r - dy * sin_r
        ry = dx * sin_r + dy * cos_r

        # Translate to center
        x = cx + rx
        y = cy + ry
        corners.append((x, y))

    return corners


def estimate_best_rectangle_for_screen(qr_data: QRPositionData,
                                     known_aspect_ratio: float = 1.45) -> Tuple[float, float, float]:
    """
    Estimate the best rectangle dimensions and rotation for a detected screen.

    Args:
        qr_data: Detected QR position data
        known_aspect_ratio: Known width/height ratio of screens

    Returns:
        (width, height, rotation) of the best-fit rectangle
    """
    if not hasattr(qr_data, 'screen_corners') or not qr_data.screen_corners:
        # Fallback: use QR data to estimate
        qr_size = (qr_data.bounding_box[2] - qr_data.bounding_box[0] +
                  qr_data.bounding_box[3] - qr_data.bounding_box[1]) / 2

        # QR is ~75% of screen height, so screen height = qr_size / 0.75
        estimated_height = qr_size / 0.75
        estimated_width = estimated_height * known_aspect_ratio

        return estimated_width, estimated_height, math.radians(qr_data.rotation)

    corners = qr_data.screen_corners

    # Calculate current dimensions
    pts = np.array(corners, dtype=np.float32)

    # Find the best-fit rectangle
    # Method: Calculate side lengths and use the average
    side_lengths = []
    for i in range(4):
        p1 = pts[i]
        p2 = pts[(i + 1) % 4]
        length = np.linalg.norm(p2 - p1)
        side_lengths.append(length)

    # Group sides: 0,2 are opposite, 1,3 are opposite
    width_estimate = (side_lengths[0] + side_lengths[2]) / 2
    height_estimate = (side_lengths[1] + side_lengths[3]) / 2

    # Ensure correct aspect ratio orientation
    if width_estimate / height_estimate < known_aspect_ratio:
        # Wrong orientation, swap
        width_estimate, height_estimate = height_estimate, width_estimate

    # Calculate rotation from the corners
    # Use the top edge (from corner 0 to corner 1)
    top_edge = pts[1] - pts[0]
    rotation = math.atan2(top_edge[1], top_edge[0])

    return width_estimate, height_estimate, rotation


def correct_perspective_distortion(qr_data_list: List[QRPositionData],
                                 known_aspect_ratio: float = 1.45) -> List[CorrectedQRData]:
    """
    Correct perspective distortion using rectangular screen constraints.

    Args:
        qr_data_list: List of detected QR position data
        known_aspect_ratio: Known width/height ratio of screens (1200/825 = 1.45)

    Returns:
        List of corrected QR position data
    """
    if len(qr_data_list) < 2:
        # Need at least 2 screens for perspective correction
        return [CorrectedQRData(
            original=qr,
            corrected_center=qr.center,
            corrected_corners=qr.corners,
            corrected_screen_corners=getattr(qr, 'screen_corners', []),
            rectangularity_score=1.0
        ) for qr in qr_data_list]

    # Step 1: Calculate rectangularity scores for all screens
    rectangularity_scores = []
    for qr in qr_data_list:
        if hasattr(qr, 'screen_corners') and qr.screen_corners:
            score = calculate_rectangularity_score(qr.screen_corners)
        else:
            score = 0.5  # Unknown, assume moderate distortion
        rectangularity_scores.append(score)

    # Step 2: Find the most rectangular screen (least distorted)
    best_screen_idx = max(range(len(rectangularity_scores)), key=lambda i: rectangularity_scores[i])
    reference_qr = qr_data_list[best_screen_idx]

    print(f"Using screen {reference_qr.hostname} as reference (rectangularity: {rectangularity_scores[best_screen_idx]:.3f})")

    # Step 3: Estimate ideal dimensions for all screens
    screen_estimates = []
    for qr in qr_data_list:
        width, height, rotation = estimate_best_rectangle_for_screen(qr, known_aspect_ratio)
        screen_estimates.append((width, height, rotation))

    # Step 4: Calculate average scale (use median to handle outliers)
    scales = [est[0] for est in screen_estimates]  # Use width for scale
    median_scale = np.median(scales)

    # Step 5: Generate ideal rectangles for all screens
    ideal_corners_all = []
    actual_corners_all = []

    for i, qr in enumerate(qr_data_list):
        if not hasattr(qr, 'screen_corners') or not qr.screen_corners:
            continue

        # Use median scale and known aspect ratio for consistency
        ideal_width = median_scale
        ideal_height = median_scale / known_aspect_ratio

        # Use the estimated rotation
        _, _, rotation = screen_estimates[i]

        # Generate ideal rectangle
        ideal_corners = calculate_ideal_rectangle(qr.center, ideal_width, ideal_height, rotation)

        ideal_corners_all.extend(ideal_corners)
        actual_corners_all.extend(qr.screen_corners)

    # Step 6: Calculate homography transformation
    if len(ideal_corners_all) >= 8:  # Need at least 4 point pairs
        actual_pts = np.array(actual_corners_all, dtype=np.float32)
        ideal_pts = np.array(ideal_corners_all, dtype=np.float32)

        try:
            # Find homography from actual to ideal
            H, mask = cv2.findHomography(actual_pts, ideal_pts, cv2.RANSAC)

            if H is not None:
                print(f"Calculated homography from {len(actual_corners_all)} point pairs")
            else:
                print("Failed to calculate homography, using identity")
                H = np.eye(3)
        except:
            print("Error calculating homography, using identity")
            H = np.eye(3)
    else:
        print("Not enough points for homography, using identity")
        H = np.eye(3)

    # Step 7: Apply correction to all QR data
    corrected_data = []
    for i, qr in enumerate(qr_data_list):
        # Apply homography to center point
        center_pt = np.array([[[qr.center[0], qr.center[1]]]], dtype=np.float32)
        corrected_center_pt = cv2.perspectiveTransform(center_pt, H)[0][0]
        corrected_center = (float(corrected_center_pt[0]), float(corrected_center_pt[1]))

        # Apply homography to QR corners
        corrected_qr_corners = []
        if qr.corners:
            corners_array = np.array([qr.corners], dtype=np.float32)
            corrected_corners_array = cv2.perspectiveTransform(corners_array, H)[0]
            corrected_qr_corners = [(float(pt[0]), float(pt[1])) for pt in corrected_corners_array]

        # Apply homography to screen corners
        corrected_screen_corners = []
        if hasattr(qr, 'screen_corners') and qr.screen_corners:
            screen_corners_array = np.array([qr.screen_corners], dtype=np.float32)
            corrected_screen_array = cv2.perspectiveTransform(screen_corners_array, H)[0]
            corrected_screen_corners = [(float(pt[0]), float(pt[1])) for pt in corrected_screen_array]

        corrected_data.append(CorrectedQRData(
            original=qr,
            corrected_center=corrected_center,
            corrected_corners=corrected_qr_corners,
            corrected_screen_corners=corrected_screen_corners,
            rectangularity_score=rectangularity_scores[i]
        ))

    return corrected_data