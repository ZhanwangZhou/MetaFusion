import time
import random
import base64
import msgpack
from datetime import timedelta
from leader.leader import Leader
from leader.storage.store import *
from utils.config import *
from utils.network import tcp_client
from utils.prompt_metadata import extract_prompt_meta
from utils.image_utils import *


class LeaderLatencyExpt(Leader):
    def __init__(self, host, port, base_dir, model_name, device, normalize):
        super().__init__(host, port, base_dir, model_name, device, normalize)

    def upload_from_json(self, record):
        if len(self.followers) == 0:
            print('No follower nodes are assigned to the leader')
            return
        try:
            image_bytes = record['image']
            photo_name = record['id'].replace('/', '+')
            latitude = record['latitude']
            longitude = record['longitude']
        except KeyError:
            return
        photo_id = hash_image_bytes(image_bytes)
        if query_by_photo_id(self.conn, photo_id):
            print(photo_name, 'has already been stored')
            return
        if 'timestamp' in record:
            timestamp = record['timestamp']
        else:
            start = datetime(2010, 1, 1)
            end = datetime(2024, 12, 31)
            delta = end - start
            rand_sec = random.randint(0, int(delta.total_seconds()))
            timestamp = start + timedelta(seconds=rand_sec)
        metadata = {
            'photo_id': photo_id,
            'photo_name': photo_name,
            'timestamp': timestamp.strftime('%Y:%m:%d %H:%M:%S'),
            'latitude': latitude,
            'longitude': longitude,
            'camera_make': None,
            'camera_model': None
        }
        digest = hashlib.sha256(photo_id.encode("utf-8")).hexdigest()
        index = int(digest, 16) % len(self.followers)
        image_b64 = base64.b64encode(image_bytes).decode("ascii")
        message = {
            'message_type': 'upload_from_json',
            'image_b64': image_b64,
            'metadata': metadata
        }
        tcp_client(self.followers[index]['host'],
                   self.followers[index]['port'],
                   message)

    def upload_from_msgpack(self, file_path):
        with open(file_path, "rb") as f:
            unpacker = msgpack.Unpacker(f, raw=False)
            for i, record in enumerate(unpacker):
                self.upload_from_json(record)
                if i % 50 == 0:
                    print(f'Inserting {i}/N photos...')
                    time.sleep(0.5)

    def search(self, prompt, output_path=None, search_mode='meta_fusion'):
        """
        Search/Get photos using given prompt under following modes:
        - 'metadata_only': Search by only metadata psql.
        - 'vector_only': Search by only vector index.
        - 'meta_fusion': Search combining metadata psql and vector index.
        """
        if len(self.followers) == 0:
            print("No follower nodes available.")
            return
        time_check1 = time.perf_counter()
        metadata = extract_prompt_meta(prompt)
        LOGGER.info('Extracted prompt meta data: %s', metadata)

        if search_mode == 'vector_only':
            # Skip pre-filtering for vector_only
            silo_ids = {f['silo_id'] for f in self.followers}
            cand_silos = [(f['silo_id'], VECTOR_SEARCH_TOP_K) for f in self.followers]
            cand_photo_ids = set()
        else:
            # Common pre-filtering for metadata_only and meta_fusion
            cand_silos = prefilter_candidate_silos(self.conn, metadata, table=self.photo_table_name)
            LOGGER.info("Candidate silos (silo_id, count): %s", cand_silos)
            if not cand_silos:
                print("No candidate silos from metadata; skip vector search.")
                return
            silo_ids = {s for (s, _) in cand_silos}
            cand_photos = fetch_photos_by_metadata(self.conn, metadata, list(silo_ids), table=self.photo_table_name)
            cand_photo_ids = {p['photo_id'] for p in cand_photos}
            # Immediately return results if metadata only search
            if search_mode == 'metadata_only':
                print(f'\n{"=" * 60}')
                print(f'Search Mode: METADATA_ONLY')
                print(f'Metadata Missing Rate: {self.metadata_missing_rate}')
                print(f'Prompt: "{prompt}"')
                print(f'Time spent: {time.perf_counter() - time_check1: .4f} s')
                print(f'Total Results: {len(cand_photos)}')
                print(f'{"=" * 60}')
                for i, photo in enumerate(cand_photos):
                    print(f'{i + 1}. Filename = {photo["photo_name"]}')
                print(f'{"=" * 60}')
                return
        time_check2 = time.perf_counter()
        query_vec = self.model.encode_text(prompt)

        # Initialize message and request info
        LOGGER.info(f"Sending vector search to {len(cand_silos)} followers")
        request_id = f"search-{int(time.time() * 10000)}"
        self.pending_client_request[request_id] = {
            'prompt': prompt,
            'recipients': silo_ids.copy(),
            'first_check': time_check1,
            'second_check': time_check2,
            'third_check': time.perf_counter(),
            'cand_photo_ids': cand_photo_ids,
            'result': [],
            'search_mode': search_mode
        }
        message = {
            'message_type': 'search',
            'request_id': request_id,
            'text': prompt,
            'query_vec': query_vec.tolist()
        }
        if output_path and os.path.isdir(output_path):
            message['message_type'] = 'get'
            message['output_path'] = output_path

        # Send message to assigned followers
        for silo_id, num in cand_silos:
            message['top_k'] = max(num * 2, VECTOR_SEARCH_TOP_K)
            follower = self.followers[silo_id]
            if follower.get('status') != 'alive':
                if 'pending_message' in follower:
                    follower['pending_message'][request_id] = message
                continue
            tcp_client(follower['host'], follower['port'], message)

    def mass_search(self, prompt_file_path):
        prompts = []
        try:
            with open(prompt_file_path, 'r') as file:
                lines = file.readlines()
                for line in lines:
                    prompts.append(line.strip())
        except FileNotFoundError:
            print(f"Error: The file '{prompt_file_path}' was not found.")
        self.pending_client_request['mass_search'] = {
            'num_prompt': len(prompts),
            'num_received': 0,
            'extract_time': 0,
            'vector_time': 0,
            'query_time': 0
        }
        for prompt in prompts:
            self.search(prompt)
            time.sleep(0.5)

    def _handle_search_result(self, message_dict, get_photo=False):
        """
        Handle text-to-image search results coming back from a follower.
        """
        silo_id = message_dict.get('silo_id')
        request_id = message_dict.get('request_id')
        partial_result = message_dict.get('results', [])
        request = self.pending_client_request.get(request_id)
        if not request:
            LOGGER.warning(f'Receiving unknown search result from follower{silo_id}')
            return
        request['recipients'].remove(silo_id)
        request['result'] += partial_result
        if len(request['recipients']) > 0:
            return

        # If received results from all assigned followers
        time_check4 = time.perf_counter()
        if 'mass_search' in self.pending_client_request:
            mass_request = self.pending_client_request['mass_search']
            mass_request['num_received'] += 1
            mass_request['extract_time'] += (request.get("second_check") -
                                             request.get("first_check"))
            mass_request['vector_time'] += (request.get("third_check") -
                                            request.get("second_check"))
            mass_request['query_time'] += time_check4 - request.get('third_check')
            if mass_request['num_received'] < mass_request['num_prompt']:
                return
            print(f'\n{"=" * 60}')
            print(f'Search Mode: MASS_META_FUSION')
            print(f'Prompt: {mass_request["num_prompt"]}')
            print(f'Time of prompt metadata extraction: '
                  f'{mass_request["extract_time"]: .4f} s')
            print(f'Time of prompt vectorization: {mass_request["vector_time"]: .4f} s')
            print(f'Time of query: {mass_request["query_time"]: .4f} s')
            print(f'\n{"=" * 60}')
            self.pending_client_request.pop('mass_search')
            return
