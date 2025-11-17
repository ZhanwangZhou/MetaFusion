# utils/geocode.py
from __future__ import annotations

from functools import lru_cache
from typing import Optional, Tuple

from geopy.geocoders import Nominatim


# 全局一个 geolocator，避免每次都新建
_geolocator: Optional[Nominatim] = None


def _get_geolocator() -> Nominatim:
    global _geolocator
    if _geolocator is None:
        # user_agent 随便写个字符串，不要为空
        _geolocator = Nominatim(user_agent="metafusion-geocoder")
    return _geolocator


@lru_cache(maxsize=256)
def geocode_location(name: str) -> Tuple[Optional[float], Optional[float]]:
    """
    把地名（比如 "Yosemite"）转换成 (lat, lon)。

    返回:
      (lat, lon) or (None, None) 如果没查到。
    """
    if not name:
        return None, None

    geolocator = _get_geolocator()
    loc = geolocator.geocode(name)
    if not loc:
        return None, None

    return float(loc.latitude), float(loc.longitude)


def geocode_bbox(name: str, radius_km: float = 50.0) -> Optional[Tuple[float, float, float, float]]:
    """
    把地名转换成一个近似的经纬度 bounding box，方便拿去做 SQL 里的 lat/lon 范围过滤。

    简化假设:
      - 1 度纬度 ≈ 111km
      - 经度也近似用一样的换算（在中纬度地区误差可以接受）

    返回:
      (min_lat, max_lat, min_lon, max_lon) 或 None
    """
    lat, lon = geocode_location(name)
    if lat is None or lon is None:
        return None

    delta_deg = radius_km / 111.0
    min_lat = lat - delta_deg
    max_lat = lat + delta_deg
    min_lon = lon - delta_deg
    max_lon = lon + delta_deg
    return min_lat, max_lat, min_lon, max_lon
