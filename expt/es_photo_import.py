import numpy as np
import requests
from datetime import datetime
from expt.es_config import *
from utils.image_utils import *
from follower.storage.photo_to_vector import ImageEmbeddingModel


def import_from_dir(image_dir):
    model = ImageEmbeddingModel()
    if not os.path.isdir(image_dir):
        print(f"The directory '{image_dir}' does not exists.")
        sys.exit(1)
    photo_paths = list_photo_paths(image_dir)
    for photo_path in photo_paths:
        try:
            image_bytes = read_image_bytes(photo_path)
        except Exception as e:
            print(f'Failed to read image from {photo_path}: {e}')
            return
        image_hash = hash_image_bytes(image_bytes)
        photo_name = os.path.basename(photo_path)
        photo_id = image_hash
        print(f'Inserting {photo_name}')
        metadata = extract_photo_metadata(photo_path)
        vector = model.encode(photo_path)
        vector = vector.reshape(1, -1).astype("float32")
        doc = {
            'photo_id': photo_id,
            'path': photo_path,
            'photo_name': photo_name,
            # 'tags': None,
            'embedding': vector.squeeze().astype(np.float32).tolist()
        }
        if metadata['timestamp']:
            doc['timestamp'] = _exif_to_iso(metadata['timestamp'])
        if metadata['latitude'] and metadata['longitude']:
            doc['location'] = {'lat': metadata['latitude'], 'lon': metadata['longitude']}
        if metadata['camera_make']:
            doc['cam_make'] = metadata['camera_make']
        if metadata['camera_model']:
            doc['cam_model'] = metadata['camera_model']
        requests.put(
            f'{ES_URL}/_doc/{photo_id}',
            auth=(ES_USERNAME, ES_PASSWORD),
            json=doc,
            verify=CERT_PATH,
            timeout=10
        )


def _exif_to_iso(ts: str) -> str:
    ts = ts.strip().strip("'\"")
    dt = datetime.strptime(ts, "%Y:%m:%d %H:%M:%S")
    return dt.isoformat()


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print('Usage: python -m expt.es_photo_import <import_directory>')
        sys.exit(1)
    import_from_dir(sys.argv[1])
