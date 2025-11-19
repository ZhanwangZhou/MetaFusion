import os
import time
import threading
import base64
from utils.prompt_metadata import PromptMetadataExtractor
from leader.storage.store import *
from utils.config import *
from utils.image_utils import *
from utils.network import tcp_server
from utils.network import tcp_client
from utils.network import udp_server


class Leader:
    def __init__(self, host, port, base_dir, model_name, device, normalize):
        self.host = host
        self.port = port
        self.signals = {'shutdown': False}
        self.followers = []

        # Unified follower index/model parameters
        self.base_dir = base_dir
        self.model_name = model_name
        self.device = device
        self.normalize = normalize
        self.metadata_extractor = PromptMetadataExtractor()

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
                'heartbeat': time.time()
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

    def search_text(self, prompt: str, candidate_silo_ids=None, top_k: int = 5):
        """
        Send a text-to-image search request to one or more followers.

        Args:
            prompt: natural language query string.
            candidate_silo_ids: list of silo_id values (typically strings from DB).
                                If None or empty, fall back to all alive followers.
            top_k: how many nearest neighbors to request from each follower.
        """
        # 1) Decide which follower silo_ids to hit.
        target_silos = set()

        if candidate_silo_ids:
            for s in candidate_silo_ids:
                try:
                    sid = int(s)
                except (TypeError, ValueError):
                    continue
                target_silos.add(sid)
        else:
            # Fallback: hit all alive followers.
            for f in self.followers:
                if f['status'] == 'alive':
                    target_silos.add(f['silo_id'])

        if not target_silos:
            print("No target followers for search_text (no candidate silos / no alive followers).")
            return

        # 2) Send the same prompt to each target follower.
        for sid in sorted(target_silos):
            follower = None
            for f in self.followers:
                if f['silo_id'] == sid:
                    follower = f
                    break

            if follower is None:
                print(f"Follower with silo_id={sid} not found in leader.followers.")
                continue

            if follower['status'] != 'alive':
                print(f"Follower {sid} is not alive (status={follower['status']}). Skip.")
                continue

            request_id = f"{sid}-{int(time.time() * 1000)}"
            message = {
                'message_type': 'search_text',
                'text': prompt,
                'top_k': top_k,
                'request_id': request_id,
            }

            try:
                tcp_client(follower['host'], follower['port'], message)
                print(
                    f"Sent search_text to follower {sid} "
                    f"(host={follower['host']}, port={follower['port']}), "
                    f"request_id={request_id}"
                )
            except ConnectionRefusedError:
                print(
                    f"Failed to send search_text to follower {sid} "
                    f"(host={follower['host']}, port={follower['port']})"
                )
