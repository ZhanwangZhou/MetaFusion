import logging

DB_NAME = 'meta_fusion'
DB_USERNAME = 'username'
DB_PASSWORD = 'password'
DB_HOST = 'localhost'
DB_PORT = 5432
DB_LEADER_TABLE_NAME = 'photos_meta'
DB_FOLLOWER_TABLE_NAME = 'vector_map'

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
LOGGER = logging.getLogger(__name__)

FOLLOWER_HEARTBEAT_INTERVAL = 2
FOLLOWER_TIMEOUT = 10

VECTOR_SEARCH_TOP_K = 5
VECTOR_SCORE_FILTER_PORTION = 0.5

ADAPTIVE_DB_PATH = 'db_path'
ADAPTIVE_PHOTO_TABLE = 'photos'
WEIGHT_TIME_HALF_LIFE = 30
