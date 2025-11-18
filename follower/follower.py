import threading
import time
import base64
from follower.storage.photo_to_vector import ImageEmbeddingModel
from follower.storage.vertex_index import FollowerFaissIndex
from utils.config import *
from utils.image_utils import *
from utils.network import tcp_server
from utils.network import tcp_client
from utils.network import udp_client


class Follower:
    def __init__(self, host, port):
        self.silo_id = None
        self.host = host
        self.port = port
        self.leader_host = None
        self.leader_port = None
        self.signals = {'shutdown': False}
        self.base_dir = None
        self.index_path = None

        self.model = None
        self.faiss_index = None

        self.heartbeat_thread = threading.Thread(target=self._heartbeat)
        self.tcp_listen_thread = threading.Thread(
            target=tcp_server, args=(host, port, self.signals, self._tcp_listen)
        )

        self.tcp_listen_thread.start()

    def register(self, leader_host, leader_port):
        """Register with the leader"""
        message = {
            'message_type': 'register',
            'host': self.host,
            'port': self.port
        }
        tcp_client(leader_host, leader_port, message)

    def _heartbeat(self):
        while not self.signals['shutdown']:
            message = {
                'message_type': 'heartbeat',
                'silo_id': self.silo_id
            }
            udp_client(self.leader_host, self.leader_port, message)
            time.sleep(FOLLOWER_HEARTBEAT_INTERVAL)

    def _tcp_listen(self, message_dict):
        match message_dict['message_type']:
            case 'register_ack':
                self._handle_register_ack(message_dict)
            case 'search_text':
                self._handle_search_text(message_dict)
            case 'upload':
                self._handle_upload(message_dict)

    def _handle_register_ack(self, message_dict):
        self.silo_id = message_dict['silo_id']
        self.leader_host = message_dict['leader_host']
        self.leader_port = message_dict['leader_port']
        self.base_dir = os.path.join(message_dict['base_dir'],
                                     f'follower{self.silo_id}')
        self.index_path = os.path.join(self.base_dir, 'faiss.index')
        self.model = ImageEmbeddingModel(message_dict['model_name'],
                                         message_dict['device'],
                                         message_dict['normalize'])
        self.faiss_index = FollowerFaissIndex(self.index_path,
                                              self.model.embedding_dim)
        self.faiss_index.save()
        LOGGER.info('Follower %d registered\n', self.silo_id)
        self.heartbeat_thread.start()

    def _handle_search_text(self, message_dict):
        """
        Handle a text-to-image search request from the leader.

        Expected message_dict format:
            {
                "message_type": "search_text",
                "text": "<user natural language query>",
                "top_k": 10,              # optional, default 10
                "request_id": "<opaque>"  # optional, echoed back in response
            }

        The follower will:
            1) Encode the text into a CLIP text embedding.
            2) Query the local FAISS index for nearest neighbors.
            3) Send results back to the leader via TCP as:
                {
                    "message_type": "search_text_result",
                    "silo_id": <int>,
                    "request_id": "<same as request>",
                    "results": [
                        {"vector_id": int, "score": float},
                        ...
                    ]
                }
        """
        if self.model is None or self.faiss_index is None:
            # Follower has not been fully initialized yet; ignore the request.
            LOGGER.warning("Received search_text before follower was initialized")
            return

        text = message_dict.get("text", "")
        if not text:
            LOGGER.warning("Received search_text with empty text")
            return

        top_k = message_dict.get("top_k", 10)
        try:
            top_k = int(top_k)
        except (TypeError, ValueError):
            top_k = 10

        # 1) Encode text into CLIP embedding
        query_vec = self.model.encode_text(text)

        # 2) Search local FAISS index
        distances, indices = self.faiss_index.search(query_vec, top_k)

        # 3) Prepare response payload
        results = []
        for idx, dist in zip(indices, distances):
            if idx == -1:
                # FAISS uses -1 as a sentinel for "no result" in some cases.
                continue
            results.append(
                {
                    "vector_id": int(idx),
                    "score": float(dist),
                }
            )

        response = {
            "message_type": "search_text_result",
            "silo_id": self.silo_id,
            "request_id": message_dict.get("request_id"),
            "results": results,
        }

        # Send results back to leader
        try:
            tcp_client(self.leader_host, self.leader_port, response)
            LOGGER.info(
                "Follower %d served search_text (top_k=%d, results=%d)",
                self.silo_id,
                top_k,
                len(results),
            )
        except ConnectionRefusedError:
            LOGGER.error(
                "Failed to send search_text_result back to leader %s:%d",
                self.leader_host,
                self.leader_port,
            )

    def _handle_upload(self, message_dict):
        photo_id = message_dict['photo_id']
        photo_name = message_dict['photo_name']
        photo_format = message_dict['photo_format']
        image_b64 = message_dict['image_b64']
        image_bytes = base64.b64decode(image_b64)
        photos_dir = os.path.join(self.base_dir, 'photos')
        os.makedirs(photos_dir, exist_ok=True)
        saved_image_path = os.path.join(photos_dir, f'{photo_id}.{photo_format.lower()}')
        save_image_bytes(image_bytes, saved_image_path)
        LOGGER.info(f'Saved uploaded image {photo_name} to {saved_image_path}')
        vector = self.model.encode(saved_image_path)
        self.faiss_index.add(vector)
        LOGGER.info(f'Added uploaded image {photo_name} to local vector index')
        metadata = extract_photo_metadata(saved_image_path)
        metadata['photo_id'] = photo_id
        metadata['photo_name'] = photo_name
        metadata['photo_format'] = photo_format
        message = {
            'message_type': 'upload_reply',
            'silo_id': self.silo_id,
            'metadata': metadata
        }
        tcp_client(self.leader_host, self.leader_port, message)
