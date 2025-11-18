import logging

DB_NAME = 'meta_fusion'
DB_USERNAME = 'jiminyang'  # 使用当前系统用户
DB_PASSWORD = ''  # 本地连接通常不需要密码
DB_HOST = 'localhost'
DB_PORT = 5432

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
LOGGER = logging.getLogger(__name__)

FOLLOWER_HEARTBEAT_INTERVAL = 2
FOLLOWER_TIMEOUT = 10
