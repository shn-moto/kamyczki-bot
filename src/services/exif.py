from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
from io import BytesIO


def get_exif_gps(image_bytes: bytes) -> tuple[float, float] | None:
    """Extract GPS coordinates from image EXIF data.

    Returns (latitude, longitude) or None if not found.
    """
    try:
        image = Image.open(BytesIO(image_bytes))
        exif_data = image._getexif()

        if not exif_data:
            return None

        gps_info = {}
        for tag_id, value in exif_data.items():
            tag = TAGS.get(tag_id, tag_id)
            if tag == "GPSInfo":
                for gps_tag_id, gps_value in value.items():
                    gps_tag = GPSTAGS.get(gps_tag_id, gps_tag_id)
                    gps_info[gps_tag] = gps_value

        if not gps_info:
            return None

        lat = _convert_to_degrees(gps_info.get("GPSLatitude"))
        lon = _convert_to_degrees(gps_info.get("GPSLongitude"))

        if lat is None or lon is None:
            return None

        if gps_info.get("GPSLatitudeRef") == "S":
            lat = -lat
        if gps_info.get("GPSLongitudeRef") == "W":
            lon = -lon

        return (lat, lon)
    except Exception:
        return None


def _convert_to_degrees(value) -> float | None:
    """Convert GPS coordinates to degrees."""
    if not value:
        return None
    try:
        d = float(value[0])
        m = float(value[1])
        s = float(value[2])
        return d + (m / 60.0) + (s / 3600.0)
    except (TypeError, IndexError, ValueError):
        return None
