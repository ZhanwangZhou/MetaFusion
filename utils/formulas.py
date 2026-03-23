# utils/formulas.py
import math
from datetime import datetime

EARTH_RADIUS_KM = 6371.0088
TOP_K_ADAPTIVE = 500


def metadata_and_vector_weight(A: float, R_v: float) -> (float, float):
    """
    Compute weight of s_m and s_v
    :param A: metadata availability
    :param R_v: vector confidence
    :return: w_m, w_v
    """
    w_m = A / (A + R_v + 1e-6)
    w_v = 1 - w_m
    return w_m, w_v


def vector_confidence(s_1: float, s_r: float) -> float:
    """
    Compute vector confidence.
    :param s_1: the highest vector similarity score in the photo collection
    :param s_r: r-th highest vector similarity score in the photo collection
    :return: R_v
    """
    return max(min((s_1 - s_r) / (s_1 + 1e-6), 1), 0)


def vector_similarity(tau: float, d_1: float, d_r: float) -> float:
    """
    Compute vector similarity score with exponential decay.
    :param tau: constant
    :param d_1: faiss distance of the first photo (from low to high)
    :param d_r: faiss distance of r-th photo
    :return: s_v
    """
    return math.exp((d_1 - d_r) / tau)


def vector_sim_constant_tau(d_1: float, d_r: float, q=0.5) -> float:
    """Constant tau for vector similarity computation"""
    return (d_1 - d_r) / math.log(q)


def vector_constant_target_ranking(n: int) -> int:
    """Ranking r used to compute vector constant tau"""
    return max(min(int(2 * math.sqrt(n)), 100), 10)


def location_similarity(distance_km: float | None, lambda_km: float) -> float:
    """
    Compute location similarity score with exponential distance decay.
    :param distance_km: distance between the target location and the photo's location
    :param lambda_km: half-life kilometers
    :return: sim_l
    """
    if distance_km is None:
        return 0.0
    if distance_km <= 0.0:
        return 1.0
    return math.exp(-math.log(2) * distance_km / lambda_km)


def time_similarity(
    photo_time: datetime | None,
    range_start: datetime,
    range_end: datetime,
    lambda_days: float,
) -> float:
    """
    Compute time similarity score with exponential time decay.
    :param photo_time: photo's date taken
    :param range_start: prompt time range start time
    :param range_end: prompt time range end time
    :param lambda_days: half-life days
    :return: sim_t
    """
    if photo_time is None:
        return 0.0
    if range_start <= photo_time <= range_end:
        return 1.0
    if photo_time < range_start:
        delta_days = (range_start - photo_time).days
    else:
        delta_days = (photo_time - range_end).days
    return math.exp(-math.log(2) * delta_days / lambda_days)


def max_query_distance(lambda_km: float, ref_lat: float, sim_min: float = 0.01) -> (float, float):
    """Max degree distance from the lat/lon queried such that sim_l >= sim_min"""
    distance_km = lambda_km * math.log2(1 / sim_min)
    delta_lat = distance_km / 111.32
    delta_lon = distance_km / (111.32 * math.cos(math.radians(ref_lat)))
    return delta_lat, delta_lon


def max_query_time_difference(lambda_days: float, sim_min: float = 0.01) -> float:
    """Max time difference from the time queried such that sim_t >= sim_min"""
    return lambda_days * math.log2(1 / sim_min)


def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance between two points (degrees) in km."""
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS_KM * c


def distance_point_to_bbox_km(lat, lon, min_lat, max_lat, min_lon, max_lon):
    """
    Distance from (lat, lon) to a bounding box.
    Returns 0 if inside.
    """
    clamped_lat = min(max(lat, min_lat), max_lat)
    clamped_lon = min(max(lon, min_lon), max_lon)
    if (min_lat <= lat <= max_lat) and (min_lon <= lon <= max_lon):
        return 0.0
    return haversine_km(lat, lon, clamped_lat, clamped_lon)


def bbox_radius_km(min_lat, max_lat, min_lon, max_lon):
    """Approximate bbox radius as half of diagonal distance."""
    diag = haversine_km(min_lat, min_lon, max_lat, max_lon)
    return diag / 2
