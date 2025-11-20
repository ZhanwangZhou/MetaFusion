import os
import time
import threading
import base64
from leader.storage.store import *
from utils.config import *
from utils.image_utils import *
from utils.prompt_metadata import extract_prompt_meta
from utils.network import tcp_server
from utils.network import tcp_client
from utils.network import udp_server


class Leader:
    def __init__(self, host, port, base_dir, model_name, device, normalize):
        self.host = host
        self.port = port
        self.signals = {'shutdown': False}
        self.followers = []
        self.pending_client_request = {}

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
        # self.tcp_listen_thread.join()
        # self.udp_listen_thread.join()
        # self.check_heartbeat_thread.join()

    def list_member(self):
        print('Leader: Host = %s, Port = %d' % (self.host, self.port))
        for i, follower in enumerate(self.followers):
            print('Follower: ID = %d, Host = %s, Port = %d, Status = %s'
                  % (i, follower['host'], follower['port'], follower['status']))

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

    def search(self, prompt, vector_search=True):
        metadata = extract_prompt_meta(prompt)

        # Filter silos by metadata
        cand_silos = prefilter_candidate_silos(self.conn, metadata)
        LOGGER.info("Candidate silos (silo_id, count): %s", cand_silos)
        if not cand_silos:
            print("No candidate silos from metadata; skip vector search.")
            return
        elif not vector_search:
            # Query specific photo_ids
            # TODO: follower subset filter / search without vector for experiment
            silo_ids = [s for (s, _) in cand_silos]
            candidates = fetch_photos_by_metadata(self.conn, metadata, silo_ids)
            LOGGER.debug(f"Found {len(candidates)} candidate photos, sample: %s",
                         candidates[:5])
            return
        silo_ids = {int(s) for (s, _) in cand_silos}
        request_id = f"search-{int(time.time() * 10000)}"
        self.pending_client_request[request_id] = {
            'arg': prompt,
            'recipient': silo_ids,
            'last_check': time.time()
        }
        message = {
            'message_type': 'search_text',
            'request_id': request_id,
            'text': prompt,
            'top_k': VECTOR_SEARCH_TOP_K,
        }
        for silo_id in silo_ids:
            follower = self.followers[silo_id]
            if follower.get('status') != 'alive':
                follower['pending_message'][request_id](message)
                continue
            tcp_client(follower['host'], follower['port'], message)

    def clear(self):
        # TODO: Clear the follower local store
        clear_all_photos(self.conn)
        LOGGER.info('Cleared photos in metadata database')

    def _check_heartbeat(self):
        while not self.signals['shutdown']:
            for follower in self.followers:
                if follower['status'] == 'alive' and\
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
            case 'search_text_result':
                self._handle_search_text_result(message_dict)

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
        LOGGER.info(f'Inserted photo {metadata["photo_name"]} into metadata database')

    def _handle_search_text_result(self, message_dict):
        """
        Handle text-to-image search results coming back from a follower.

        Expected message_dict format (from follower._handle_search_text):
            {
                "message_type": "search_text_result",
                "silo_id": int,
                "request_id": str or None,
                "results": [
                    {"vector_id": int, "score": float},
                    ...
                ]
            }
        """
        silo_id = message_dict.get('silo_id')
        request_id = message_dict.get('request_id')
        results = message_dict.get('results', [])

        print(f"[search_text_result] from follower {silo_id}, request_id={request_id}")
        if not results:
            print("  (no results)")
            return

        for r in results:
            vid = r.get('vector_id')
            score = r.get('score')
            photo_id = r.get('photo_id')
            photo_name = r.get('photo_name')
            has_image = 'image_b64' in r

            line = f"  vector_id={vid}, score={score}"
            if photo_id:
                line += f", photo_id={photo_id}"
            if photo_name:
                line += f", photo_name={photo_name}"
            if has_image:
                line += " [image_b64 attached]"
            print(line)
