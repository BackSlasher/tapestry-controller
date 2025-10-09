"""QR code debug functionality for analyzing and visualizing QR detection."""

from typing import Any, Dict, List

import PIL.Image
import PIL.ImageDraw as ImageDraw

from .position_detection import detect_qr_positions


def analyze_qr_image(
    image: PIL.Image.Image,
) -> tuple[PIL.Image.Image, List[Dict[str, Any]]]:
    """
    Analyze an image for QR codes and create debug visualization.

    Args:
        image: PIL Image to analyze

    Returns:
        Tuple of (debug_image, qr_info_list)
        - debug_image: PIL Image with debug visualization overlays
        - qr_info_list: List of dictionaries containing QR code information
    """
    # Detect QR codes and get their positions
    qr_data = detect_qr_positions(image)

    # Create debug visualization
    debug_image = image.copy()
    draw = ImageDraw.Draw(debug_image)

    debug_info = []

    for i, qr in enumerate(qr_data):
        # Draw QR outline by connecting corner points
        if hasattr(qr, "corners") and qr.corners and len(qr.corners) >= 4:
            # Draw lines connecting the QR corners to form the actual detected shape
            corners = qr.corners
            for j in range(len(corners)):
                start_point = corners[j]
                end_point = corners[
                    (j + 1) % len(corners)
                ]  # Connect to next corner, wrap to first
                draw.line([start_point, end_point], fill="red", width=3)

        # Draw QR corner markers - highlight first corner with bold circle
        if hasattr(qr, "corners") and qr.corners and len(qr.corners) >= 4:
            for j, (x, y) in enumerate(qr.corners):
                # Make the first QR corner bold (larger and different color)
                if j == 0:
                    radius = 8
                    draw.ellipse(
                        [(x - radius, y - radius), (x + radius, y + radius)],
                        outline="red",
                        fill="yellow",
                        width=3,
                    )
                else:
                    radius = 4
                    draw.ellipse(
                        [(x - radius, y - radius), (x + radius, y + radius)],
                        outline="red",
                        fill="pink",
                        width=1,
                    )

        # Draw screen area if available
        if (
            hasattr(qr, "screen_corners")
            and qr.screen_corners
            and len(qr.screen_corners) >= 4
        ):
            # Draw screen boundary as thick polygon
            screen_points = [(x, y) for x, y in qr.screen_corners]
            draw.polygon(screen_points, outline="blue", width=4)

            # Draw semi-transparent fill to highlight screen area
            try:
                # Create a temporary image for the fill
                overlay = PIL.Image.new("RGBA", debug_image.size, (0, 0, 0, 0))
                overlay_draw = ImageDraw.Draw(overlay)
                overlay_draw.polygon(
                    screen_points, fill=(0, 0, 255, 30)
                )  # Semi-transparent blue
                debug_image = PIL.Image.alpha_composite(
                    debug_image.convert("RGBA"), overlay
                ).convert("RGB")
                draw = ImageDraw.Draw(debug_image)  # Recreate draw object
            except Exception:
                pass  # Fallback if alpha blending fails

            # Draw corner markers with numbers
            for j, (x, y) in enumerate(qr.screen_corners):
                # Make the first corner (j=0) twice as large
                radius = 12 if j == 0 else 6
                draw.ellipse(
                    [(x - radius, y - radius), (x + radius, y + radius)],
                    outline="blue",
                    fill="lightblue",
                    width=2,
                )
                # Add corner number (adjust text position for larger first corner)
                text_offset = 14 if j == 0 else 8
                draw.text((x + text_offset, y - text_offset), str(j + 1), fill="blue")

            # Add screen type label near the screen center
            if len(screen_points) >= 4:
                center_x = sum(x for x, y in screen_points) / len(screen_points)
                center_y = sum(y for x, y in screen_points) / len(screen_points)
                screen_label = f"Screen: {qr.screen_type}"
                draw.text((center_x - 30, center_y), screen_label, fill="blue")

        # Add label using bounding box for positioning
        min_x, min_y, max_x, max_y = qr.bounding_box
        label = f"QR{i+1}"
        draw.text((min_x, min_y - 20), label, fill="red")

        # Collect debug info
        qr_info = {
            "id": i + 1,
            "hostname": qr.hostname,
            "screen_type": qr.screen_type,
            "center": qr.center,
            "rotation": qr.rotation,
            "bbox": {
                "x": min_x,
                "y": min_y,
                "width": max_x - min_x,
                "height": max_y - min_y,
            },
        }

        # Add screen corners if available
        if hasattr(qr, "screen_corners") and qr.screen_corners:
            qr_info["screen_corners"] = qr.screen_corners

        debug_info.append(qr_info)

    return debug_image, debug_info
