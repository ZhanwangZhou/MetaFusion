import os
import hashlib
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
from io import BytesIO


def read_image_bytes(image_path: str) -> bytes:
    """
    Safely read an image file and return raw bytes.
    """
    if not os.path.exists(image_path) or not os.path.isfile(image_path):
        raise FileNotFoundError(f"Image path does not exist")
    try:
        with open(image_path, 'rb') as f:
            data = f.read()
            if not data:
                raise IOError(f"File is empty or unreadable")
    except Exception as e:
        raise IOError(e)
    return data


def save_image_bytes(image_bytes: bytes, output_path: str):
    """
    Save raw bytes as a image file.
    """
    with open(output_path, "wb") as f:
        f.write(image_bytes)


def get_format_from_bytes(image_bytes: bytes):
    """
    Get file format of the image.
    """
    return Image.open(BytesIO(image_bytes)).format


def hash_image_bytes(data: bytes, algorithm: str = "sha256") -> str:
    """
    Compute a stable hash of the image file contents.
    """
    h = hashlib.new(algorithm)
    h.update(data)
    return h.hexdigest()


def extract_photo_metadata(image_path: str) -> dict:
    """
    Extract photo metadata of the image at image_path.
    """
    exif_data = _extract_exif(image_path)
    timestamp = exif_data.get('DateTimeOriginal') or exif_data.get('DateTime') \
                or None
    lat, lon = _extract_gps(exif_data)
    return {
        'timestamp': timestamp,
        'latitude': lat,
        'longitude': lon,
        'camera_make': exif_data.get('Make'),
        'camera_model': exif_data.get('Model'),
    }


def _extract_exif(image_path: str) -> dict:
    """
    Extract EXIF metadata of the image at image_path.
    """
    image = Image.open(image_path)
    exif_info = image._getexif()
    if exif_info is None:
        return {}
    exif_data = {
        TAGS[k]: v
        for k, v in exif_info.items()
        if k in TAGS
    }
    return exif_data


def _extract_gps(exif_data):
    """
    Extract latitude and longitude in decimal degree from the EXIF metadata.
    """
    gps_info = exif_data.get('GPSInfo')
    if not gps_info:
        return None, None
    gps_data = {
        GPSTAGS.get(key, key): gps_info[key]
        for key in gps_info
    }

    if 'GPSLatitude' in gps_data and 'GPSLatitudeRef' in gps_data:
        lat = _convert_to_degrees(gps_data['GPSLatitude'])
        if gps_data['GPSLatitudeRef'] == 'S':
            lat = -lat
    else:
        lat = None

    if 'GPSLongitude' in gps_data and 'GPSLongitudeRef' in gps_data:
        lon = _convert_to_degrees(gps_data['GPSLongitude'])
        if gps_data['GPSLongitudeRef'] == 'W':
            lon = -lon
    else:
        lon = None

    return lat, lon


def _convert_to_degrees(gps_data_slice):
    """
    Convert EXIF GPS data to standard decimal degrees.
    """
    d, m, s = gps_data_slice
    return d + (m / 60.0) + (s / 3600.0)
