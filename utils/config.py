import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
LOGGER = logging.getLogger(__name__)

FOLLOWER_HEARTBEAT_INTERVAL = 2
FOLLOWER_TIMEOUT = 10
