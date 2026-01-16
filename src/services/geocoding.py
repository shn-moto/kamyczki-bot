import httpx
import logging

logger = logging.getLogger(__name__)

NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"
NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"


async def get_location_from_gps(lat: float, lon: float) -> dict | None:
    """Get location info (ZIP, city, country) from GPS coordinates using Nominatim.

    Returns dict with: zip_code, city, country, display_name
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                NOMINATIM_REVERSE_URL,
                params={
                    "lat": lat,
                    "lon": lon,
                    "format": "json",
                    "addressdetails": 1,
                },
                headers={
                    "User-Agent": "kamyczki-bot/1.0"
                },
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()

            address = data.get("address", {})

            result = {
                "zip_code": address.get("postcode"),
                "city": address.get("city") or address.get("town") or address.get("village"),
                "country": address.get("country"),
                "display_name": data.get("display_name"),
            }

            logger.info(f"Geocoding {lat}, {lon} -> {result}")
            return result

    except Exception as e:
        logger.error(f"Geocoding failed: {e}")
        return None


async def get_coords_from_zip(zip_code: str) -> tuple[float, float] | None:
    """Get coordinates from ZIP/postal code using Nominatim.

    Returns (latitude, longitude) or None if not found.
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                NOMINATIM_SEARCH_URL,
                params={
                    "postalcode": zip_code,
                    "format": "json",
                    "limit": 1,
                },
                headers={
                    "User-Agent": "kamyczki-bot/1.0"
                },
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()

            if data and len(data) > 0:
                lat = float(data[0]["lat"])
                lon = float(data[0]["lon"])
                logger.info(f"ZIP geocoding {zip_code} -> {lat}, {lon}")
                return lat, lon

            logger.warning(f"ZIP geocoding {zip_code} -> not found")
            return None

    except Exception as e:
        logger.error(f"ZIP geocoding failed: {e}")
        return None
