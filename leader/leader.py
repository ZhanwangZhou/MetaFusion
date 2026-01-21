import sys
import time
import random
import threading
import base64
import msgpack
from datetime import timedelta
from typing import List, Dict, Optional, Any
from leader.storage.store import *
from utils.config import *
from utils.image_utils import *
from utils.prompt_metadata import extract_prompt_meta
from utils.photo_to_vector import ImageEmbeddingModel
from utils.network import tcp_server
from utils.network import tcp_client
from utils.network import udp_server


class Leader:
    def __init__(self, host, port, base_dir, model_name, device, normalize):
        self.host = host
        self.port = port
        self.signals = {'shutdown': False}
        self.followers: List[Dict[str, Optional[Any]]] = []
        self.pending_client_request: Dict[str, Dict[str, Optional[Any]]] = {}
        self.model = ImageEmbeddingModel(model_name=model_name,
                                         device=device,
                                         normalize=normalize)

        # Unified follower index/model parameters
        self.base_dir = base_dir
        self.model_name = model_name
        self.device = device
        self.normalize = normalize

        self.check_heartbeat_thread = threading.Thread(target=self._check_heartbeat)
        self.udp_listen_thread = threading.Thread(
            target=udp_server, args=(host, port, self.signals, self._udp_listen)
        )
        self.tcp_listen_thread = threading.Thread(
            target=tcp_server, args=(host, port, self.signals, self._tcp_listen)
        )

        self.check_heartbeat_thread.start()
        self.udp_listen_thread.start()
        self.tcp_listen_thread.start()
        self.conn = init_metadata_table()
        LOGGER.info('Leader initialized')

    def list_member(self):
        print('Leader: Host = %s, Port = %d' % (self.host, self.port))
        for i, follower in enumerate(self.followers):
            print('Follower: ID = %d, Host = %s, Port = %d, Status = %s'
                  % (i, follower['host'], follower['port'], follower['status']))

    def list_num_photo(self):
        num = query_photo_num(self.conn)[0]
        print(f'Num of photos stored: {num}')

    def upload(self, image_path):
        if len(self.followers) == 0:
            print('No follower nodes are assigned to the leader')
            return
        try:
            image_bytes = read_image_bytes(image_path)
        except Exception as e:
            print(f'Failed to read image from {image_path}: {e}')
            return
        image_hash = hash_image_bytes(image_bytes)
        photo_name = os.path.basename(image_path)
        photo_id = image_hash  # can be updated later with upload_time/user_id
        if query_by_photo_id(self.conn, photo_id):
            print(photo_name, 'has already been stored')
            return
        digest = hashlib.sha256(photo_id.encode("utf-8")).hexdigest()
        index = int(digest, 16) % len(self.followers)
        image_b64 = base64.b64encode(image_bytes).decode("ascii")
        message = {
            'message_type': 'upload',
            'photo_id': photo_id,
            'photo_name': photo_name,
            'photo_format': get_format_from_bytes(image_bytes),
            'image_b64': image_b64
        }
        tcp_client(self.followers[index]['host'],
                   self.followers[index]['port'],
                   message)

    def mass_upload(self, image_dir):
        photo_paths = list_photo_paths(image_dir)
        for i, photo_path in enumerate(photo_paths):
            self.upload(photo_path)
            if i % 50 == 0:
                time.sleep(1)

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
            cand_silos = prefilter_candidate_silos(self.conn, metadata)
            LOGGER.info("Candidate silos (silo_id, count): %s", cand_silos)
            if not cand_silos:
                print("No candidate silos from metadata; skip vector search.")
                return
            silo_ids = {s for (s, _) in cand_silos}
            cand_photos = fetch_photos_by_metadata(self.conn, metadata, list(silo_ids))
            cand_photo_ids = {p['photo_id'] for p in cand_photos}
            # Immediately return results if metadata only search
            if search_mode == 'metadata_only':
                print(f'\n{"=" * 60}')
                print(f'Search Mode: METADATA_ONLY')
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

    def clear(self):
        clear_all_photos(self.conn)
        LOGGER.info('Cleared photos in metadata database')
        message = {'message_type': 'clear'}
        for follower in self.followers:
            tcp_client(follower['host'], follower['port'], message)

    def quit(self):
        message = {'message_type': 'quit'}
        for follower in self.followers:
            tcp_client(follower['host'], follower['port'], message)
        self.signals['shutdown'] = True
        self.tcp_listen_thread.join()
        self.udp_listen_thread.join()
        self.check_heartbeat_thread.join()
        sys.exit(0)

    def _check_heartbeat(self):
        while not self.signals['shutdown']:
            for follower in self.followers:
                if follower['status'] == 'alive' and \
                        time.time() - follower['heartbeat'] > FOLLOWER_TIMEOUT:
                    follower['status'] = 'dead'
                    LOGGER.info('Set follower %d to dead' % (follower['silo_id']))
            time.sleep(FOLLOWER_HEARTBEAT_INTERVAL)

    def _udp_listen(self, message_dict):
        match message_dict['message_type']:
            case 'heartbeat':
                self.followers[message_dict['silo_id']]['heartbeat'] = time.time()

    def _tcp_listen(self, message_dict):
        match message_dict['message_type']:
            case 'register':
                self._handle_register(message_dict)
            case 'upload_reply':
                self._handle_upload_reply(message_dict)
            case 'search_result':
                self._handle_search_result(message_dict)
            case 'get_result':
                self._handle_search_result(message_dict, get_photo=True)

    def _handle_register(self, message_dict):
        host = message_dict['host']
        port = message_dict['port']
        for i, follower in enumerate(self.followers):
            if follower['host'] == host and follower['port'] == port:
                silo_id = i
                follower['status'] = 'alive'
                follower['heartbeat'] = time.time()
                break
        else:
            silo_id = len(self.followers)
            new_follower = {
                'silo_id': silo_id,
                'host': host,
                'port': port,
                'status': 'alive',
                'heartbeat': time.time(),
                'pending_message': {}
            }
            self.followers.append(new_follower)
        message = {
            'message_type': 'register_ack',
            'silo_id': silo_id,
            'leader_host': self.host,
            'leader_port': self.port,
            'base_dir': self.base_dir,
            'model_name': self.model_name,
            'device': self.device,
            'normalize': self.normalize
        }
        try:
            tcp_client(host, port, message)
            LOGGER.info('Ack registration of follower %d (host = %s, port = %d)'
                        % (silo_id, host, port))
        except ConnectionRefusedError:
            self.followers[silo_id]['status'] = 'dead'

    def _handle_upload_reply(self, message_dict):
        silo_id = message_dict['silo_id']
        metadata = message_dict['metadata']
        insert_new_photo(self.conn, silo_id, metadata)
        LOGGER.info(f'Inserted photo {metadata["photo_name"]} into metadata database.'
                    f'Assigned to follower {silo_id}')

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
        search_mode = request.get('search_mode', 'unknown')
        print(f'\n{"="*60}')
        print(f'Search Mode: {search_mode.upper()}')
        print(f'Prompt: "{request["prompt"]}"')
        print(f'Time Spent: {time_check4 - request.get("second_check"): .4f} s')

        # Post filtering and print result photos
        results = request['result']
        results = sorted(results, key=lambda x: x.get('score', 0))
        results = results[:int(len(results) * VECTOR_SCORE_FILTER_PORTION)]
        if search_mode == 'meta_fusion':
            results = [
                r for r in results if r.get('photo_id') in request.get('cand_photo_ids')
            ]
        print(f'Total Results: {len(results)}')
        print(f'{"="*60}')
        if not request['result']:
            print("(no results)")
        else:
            i = 1
            for r in results:
                score = r.get('score')
                photo_name = r.get('photo_name')
                print(f'{i}. Filename = {photo_name}, Score = {score: .4f}')
                if get_photo:
                    image_bytes = base64.b64decode(r['image_b64'])
                    output_path = os.path.join(message_dict['output_path'], photo_name)
                    save_image_bytes(image_bytes, output_path)
                    print(f'   Saved to {output_path}')
                i += 1
        print(f'{"="*60}\n')
        self.pending_client_request.pop(request_id)
