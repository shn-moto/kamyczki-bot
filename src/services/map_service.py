"""Service for generating map images with stone history."""
from staticmap import StaticMap, Line, CircleMarker
from io import BytesIO


def generate_stone_map_image(history: list, stone_name: str) -> bytes | None:
    """Generate PNG map image with stone movement history.

    Args:
        history: List of StoneHistory objects with lat/lon/created_at
        stone_name: Name of the stone for the title

    Returns:
        PNG image as bytes, or None if no coordinates available
    """
    # Filter entries with coordinates
    points = [
        {
            "lat": h.latitude,
            "lon": h.longitude,
            "date": h.created_at,
        }
        for h in history
        if h.latitude is not None and h.longitude is not None
    ]

    if not points:
        return None

    # Sort by date
    points.sort(key=lambda x: x["date"])

    # Create map with reasonable size
    m = StaticMap(800, 600, url_template="https://tile.openstreetmap.org/{z}/{x}/{y}.png")

    # Add markers
    for i, point in enumerate(points):
        lon, lat = point["lon"], point["lat"]

        # First point - green, last - red, others - blue
        if i == 0:
            color = "#22c55e"  # green
            size = 12
        elif i == len(points) - 1:
            color = "#ef4444"  # red
            size = 12
        else:
            color = "#3b82f6"  # blue
            size = 8

        marker = CircleMarker((lon, lat), color, size)
        m.add_marker(marker)

    # Add route line if more than 1 point
    if len(points) > 1:
        coordinates = [(p["lon"], p["lat"]) for p in points]
        line = Line(coordinates, "#3b82f6", 3)
        m.add_line(line)

    # Render to PNG
    image = m.render()

    # Save to bytes
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)

    return buffer.getvalue()
