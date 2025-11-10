import threading
from utils.network import tcp_server


class Follower:
    def __init__(self, host, port):
        self.silo_id = None
        self.host = host
        self.port = port
        self.leader_host = None
        self.leader_port = None
        self.signals = {'shutdown': False}
        self.tcp_listen = threading.Thread(
            target=tcp_server, args=(self.host, self.port, self.signals, self.handle_tcp)
        )

    def _connect(self):
        pass

    def handle_tcp(self):
        pass

