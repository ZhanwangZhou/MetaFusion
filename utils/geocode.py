# utils/geocode.py
from __future__ import annotations

from functools import lru_cache
from typing import Optional, Tuple

from geopy.geocoders import Nominatim


# A global geolocator to avoid creating one each time
_geolocator: Optional[Nominatim] = None


def _get_geolocator() -> Nominatim:
    global _geolocator
    if _geolocator is None:
        # user_agent should be any non-empty string
        _geolocator = Nominatim(user_agent="metafusion-geocoder")
    return _geolocator


@lru_cache(maxsize=256)
def geocode_location(name: str) -> Tuple[Optional[float], Optional[float], Tuple[Optional[float]]]:
    """
        Convert a place name (e.g., "Yosemite") to (lat, lon).

        Returns:
            (lat, lon) or (None, None) if not found.
    """
    if not name:
        return None, None, (None,)

    geolocator = _get_geolocator()
    loc = geolocator.geocode(name, addressdetails=True)
    if not loc:
        return None, None, (None,)
    raw_data = loc.raw
    # loc_type = raw_data.get('addresstype') or raw_data.get('type')
    bbox = tuple(raw_data.get('boundingbox'))
    bbox = tuple(float(b) or None for b in bbox)

    return float(loc.latitude), float(loc.longitude), bbox


def geocode_bbox(name: str, radius_km: float = 50.0) -> Optional[Tuple[float, float, float, float]]:
    """
        Convert a place name into an approximate latitude/longitude bounding box,
        suitable for SQL lat/lon range filtering.

        Simplifying assumptions:
            - 1 degree latitude ≈ 111km
            - longitude uses the same conversion (acceptable error at mid-latitudes)

        Returns:
            (min_lat, max_lat, min_lon, max_lon) or None
    """
    lat, lon, _ = geocode_location(name)
    if lat is None or lon is None:
        return None

    delta_deg = radius_km / 111.0
    min_lat = lat - delta_deg
    max_lat = lat + delta_deg
    min_lon = lon - delta_deg
    max_lon = lon + delta_deg
    return min_lat, max_lat, min_lon, max_lon
