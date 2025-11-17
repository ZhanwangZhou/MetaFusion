import os
import hashlib
from PIL import Image
from io import BytesIO


def read_image_bytes(image_path: str) -> bytes:
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
    with open(output_path, "wb") as f:
        f.write(image_bytes)


def get_format_from_bytes(image_bytes):
    return Image.open(BytesIO(image_bytes)).format


def hash_image_bytes(data: bytes, algorithm: str = "sha256") -> str:
    h = hashlib.new(algorithm)
    h.update(data)
    return h.hexdigest()


