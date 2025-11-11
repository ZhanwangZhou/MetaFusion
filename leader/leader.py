import time
import threading
from utils.config import *
from utils.network import tcp_server
from utils.network import tcp_client
from utils.network import udp_server


class Leader:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.signals = {'shutdown': False}
        self.followers = []
        self.check_heartbeat_thread = threading.Thread(self._check_heartbeat)
        self.udp_listen_thread = threading.Thread(
            target=udp_server, args=(host, port, self.signals, self._udp_listen)
        )
        self.tcp_listen_thread = threading.Thread(
            target=tcp_server, args=(host, port, self.signals, self._tcp_listen)
        )
        self.udp_listen_thread.start()
        self.tcp_listen_thread.start()
        self.tcp_listen_thread.join()
        self.udp_listen_thread.join()

    def _check_heartbeat(self):
        while not self.signals['shutdown']:
            for follower in self.followers:
                if time.time() - follower['heartbeat'] > FOLLOWER_TIMEOUT:
                    follower['status'] = 'dead'
                    LOGGER.info('Set follower %d to dead', follower['silo_id'])
        time.sleep(FOLLOWER_HEARTBEAT_INTERVAL)

    def _udp_listen(self, message_dict):
        match message_dict['message_type']:
            case 'heartbeat':
                self.followers[message_dict['silo_id']]['heartbeat'] = time.time()

    def _tcp_listen(self, message_dict):
        match message_dict['message_type']:
            case 'register':
                self._handle_register(message_dict)

    def _handle_register(self, message_dict):
        host = message_dict['host']
        port = message_dict['port']
        for i, follower in enumerate(self.followers):
            if follower['host'] == 'host' and follower['port'] == port:
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
            'silo_id': silo_id
        }
        try:
            tcp_client(host, port, message)
            LOGGER.info('Ack registration of follower %d (host = %s, port = %d)',
                        silo_id, host, port)
        except ConnectionRefusedError:
            self.followers[silo_id]['status'] = 'dead'
