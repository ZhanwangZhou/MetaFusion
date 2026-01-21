import random
import numpy as np
import requests
import msgpack
from datetime import datetime, timedelta
from expt.es_config import *
from utils.image_utils import *
from utils.photo_to_vector import ImageEmbeddingModel


def import_from_dir(image_dir):
    model = ImageEmbeddingModel()
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
        vector = model.encode(image_path=photo_path)
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


def import_from_msgpack(msgpack_path):
    model = ImageEmbeddingModel()
    with open(msgpack_path, "rb") as f:
        unpacker = msgpack.Unpacker(f, raw=False)
        for i, record in enumerate(unpacker):
            if i % 100 == 0:
                print(f'Inserting {i}/N photos...')
            try:
                image_bytes = record['image']
                photo_name = record['id'].replace('/', '+')
                latitude = record['latitude']
                longitude = record['longitude']
            except KeyError:
                continue
            photo_id = hash_image_bytes(image_bytes)
            if 'timestamp' in record:
                timestamp = record['timestamp']
            else:
                start = datetime(2010, 1, 1)
                end = datetime(2024, 12, 31)
                delta = end - start
                rand_sec = random.randint(0, int(delta.total_seconds()))
                timestamp = start + timedelta(seconds=rand_sec)
            vector = model.encode(image_bytes=image_bytes)
            vector = vector.reshape(1, -1).astype("float32")
            doc = {
                'photo_id': photo_id,
                'photo_name': photo_name,
                'location': {'lat': latitude, 'lon': longitude},
                'timestamp': _exif_to_iso(timestamp.strftime('%Y:%m:%d %H:%M:%S')),
                'embedding': vector.squeeze().astype(np.float32).tolist()
            }
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
    file_path = sys.argv[1]
    if os.path.isdir(file_path):
        import_from_dir(file_path)
    elif os.path.isfile(file_path):
        import_from_msgpack(file_path)
    else:
        print(f"The directory/file '{file_path}' does not exists.")
        sys.exit(1)

