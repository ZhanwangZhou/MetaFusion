import sys
import base64
import threading
import time
from typing import Optional, Any

import psycopg2.extensions

from follower.storage.store import *
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
        self.photos_dir = None
        self.index_path = None

        self.model: Optional[ImageEmbeddingModel] = None
        self.faiss_index: Optional[FollowerFaissIndex] = None
        self.conn: Optional[psycopg2.extensions.connection] = None
        self.psql_table_name = DB_FOLLOWER_TABLE_NAME

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
            case 'search':
                self._handle_search(message_dict)
            case 'get':
                self._handle_search(message_dict, get_photo=True)
            case 'upload':
                self._handle_upload(message_dict)
            case 'upload_from_json':
                self._handle_upload_from_json(message_dict)
            case 'clear':
                self._handle_clear()
            case 'quit':
                self._handle_quit()

    def _handle_register_ack(self, message_dict):
        self.silo_id = message_dict['silo_id']
        self.leader_host = message_dict['leader_host']
        self.leader_port = message_dict['leader_port']
        self.base_dir = os.path.join(message_dict['base_dir'],
                                     f'follower{self.silo_id}')
        os.makedirs(self.base_dir, exist_ok=True)
        self.photos_dir = os.path.join(self.base_dir, 'photos')
        os.makedirs(self.photos_dir, exist_ok=True)
        self.index_path = os.path.join(self.base_dir, 'faiss.index')

        self.model = ImageEmbeddingModel(message_dict['model_name'],
                                         message_dict['device'],
                                         message_dict['normalize'])
        self.faiss_index = FollowerFaissIndex(self.index_path,
                                              self.model.embedding_dim)
        self.faiss_index.save()
        self.psql_table_name = f'{DB_FOLLOWER_TABLE_NAME}{self.silo_id}'
        self.conn = init_vector_table(table=self.psql_table_name)

        LOGGER.info('Follower %d registered (base_dir=%s, index_path=%s)\n',
                    self.silo_id, self.base_dir, self.index_path)
        self.heartbeat_thread.start()

    def _handle_search(self, message_dict, get_photo=False):
        """
        Handle a text-to-image search request from the leader.
        """
        if self.model is None or self.faiss_index is None:
            # Follower has not been fully initialized yet; ignore the request.
            LOGGER.warning("Received search_text before follower was initialized")
            return

        prompt = message_dict.get('text', '')
        query_vec = self.model.encode_text(prompt)
        distances, indices = self.faiss_index.search(query_vec, message_dict['top_k'])

        results = []
        for idx, dist in zip(indices, distances):
            if idx == -1:
                # FAISS uses -1 as a sentinel for "no result" in some cases.
                continue
            query_result = query_by_vector_id(self.conn, idx, table=self.psql_table_name)
            if query_result:
                _, photo_id, photo_name, photo_format, saved_path = query_result
            else:
                continue
            item = {
                "vector_id": int(idx),
                "score": float(dist),
                "photo_id": photo_id,
                "photo_name": photo_name,
                "photo_format": photo_format
            }
            # Optionally include the raw image bytes as base64 so that the
            # leader can reconstruct or save the original photo.
            if get_photo:
                try:
                    image_bytes = read_image_bytes(saved_path)
                    item["image_b64"] = base64.b64encode(image_bytes).decode("ascii")
                except Exception as e:
                    LOGGER.warning("Failed to read image for vector_id=%d at %s: %s",
                                   idx, saved_path, e,)
            results.append(item)

        message = {
            "message_type": "get_result" if get_photo else "search_result",
            "silo_id": self.silo_id,
            "request_id": message_dict.get("request_id"),
            "output_path": message_dict.get("output_path"),
            "results": results,
        }
        tcp_client(self.leader_host, self.leader_port, message)
        LOGGER.info(f'Sent search result for prompt {prompt} to the leader')

    def _handle_upload(self, message_dict):
        photo_id = message_dict['photo_id']
        photo_name = message_dict['photo_name']
        photo_format = message_dict['photo_format']
        image_b64 = message_dict['image_b64']
        image_bytes = base64.b64decode(image_b64)
        saved_image_path = os.path.join(self.photos_dir, f'{photo_id}.{photo_format.lower()}')
        save_image_bytes(image_bytes, saved_image_path)
        LOGGER.info(f'Saved uploaded image {photo_name} to {saved_image_path}')
        vector = self.model.encode(saved_image_path)
        vector_id = self.faiss_index.add(vector)
        self.faiss_index.save()

        insert_data = {
            'vector_id': vector_id,
            'photo_id': photo_id,
            'photo_name': photo_name,
            'photo_format': photo_format,
            'saved_path': saved_image_path,
        }
        insert_new_photo_vector(self.conn, insert_data, table=self.psql_table_name)
        LOGGER.info('Added uploaded image %s to local vector index as vector_id=%d',
                    photo_name, vector_id, )

        metadata = extract_photo_metadata(saved_image_path)
        metadata = metadata | insert_data
        message = {
            'message_type': 'upload_reply',
            'silo_id': self.silo_id,
            'metadata': metadata
        }
        tcp_client(self.leader_host, self.leader_port, message)

    def _handle_upload_from_json(self, message_dict):
        metadata = message_dict['metadata']
        photo_id = metadata['photo_id']
        photo_name = metadata['photo_name']
        image_b64 = message_dict['image_b64']
        image_bytes = base64.b64decode(image_b64)
        saved_image_path = os.path.join(self.photos_dir, f'{photo_name}')
        save_image_bytes(image_bytes, saved_image_path)
        LOGGER.info(f'Saved uploaded image {photo_name} to {saved_image_path}')
        vector = self.model.encode(saved_image_path)
        vector_id = self.faiss_index.add(vector)
        self.faiss_index.save()

        insert_data = {
            'vector_id': vector_id,
            'photo_id': photo_id,
            'photo_name': photo_name,
            'photo_format': 'jpg',
            'saved_path': saved_image_path,
        }
        insert_new_photo_vector(self.conn, insert_data, table=self.psql_table_name)
        LOGGER.info('Added uploaded image %s to local vector index as vector_id=%d',
                    photo_name, vector_id, )
        message = {
            'message_type': 'upload_reply',
            'silo_id': self.silo_id,
            'metadata': metadata
        }
        tcp_client(self.leader_host, self.leader_port, message)

    def _handle_clear(self):
        self.faiss_index.clear()
        clear_all(self.conn, table=self.psql_table_name)
        for filename in os.listdir(self.photos_dir):
            filepath = os.path.join(self.photos_dir, filename)
            if os.path.isfile(filepath):
                try:
                    os.remove(filepath)
                except Exception as e:
                    LOGGER.warning(f'Failed to remove {filepath}', e)
        LOGGER.info("Cleared the vector index and all photos")

    def _handle_quit(self):
        self.signals['shutdown'] = True
        self.heartbeat_thread.join()
        LOGGER.info(f'Follower {self.silo_id} exits with 0')
        sys.exit(0)
