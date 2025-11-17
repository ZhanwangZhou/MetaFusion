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
        self.base_dir = 'state/follower/'  # TODO: update this with directory from cli

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
            case 'upload':
                self._handle_upload(message_dict)

    def _handle_register_ack(self, message_dict):
        self.model = ImageEmbeddingModel(message_dict['model_name'],
                                         message_dict['device'],
                                         message_dict['normalize'])
        self.faiss_index = FollowerFaissIndex(message_dict['index_path'],
                                              self.model.embedding_dim)
        self.faiss_index.save()
        self.silo_id = message_dict['silo_id']
        self.leader_host = message_dict['leader_host']
        self.leader_port = message_dict['leader_port']
        LOGGER.info('Follower %d registered\n', self.silo_id)
        self.heartbeat_thread.start()

    def _handle_upload(self, message_dict):
        photo_id = message_dict['photo_id']
        photo_format = message_dict['photo_format']
        image_b64 = message_dict['image_b64']
        image_bytes = base64.b64decode(image_b64)
        os.makedirs(f'{self.base_dir}/photos/', exist_ok=True)
        save_image_bytes(image_bytes, f'{self.base_dir}/photos/{photo_id}.{photo_format}')
