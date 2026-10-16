import os
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv('BASE_URL', 'http://localhost:5173')
NUM_USERS = int(os.getenv('NUM_USERS', '100'))
SPAWN_RATE = int(os.getenv('SPAWN_RATE', '10'))
TEST_USER_PREFIX = os.getenv('TEST_USER_PREFIX', 'loadtest_')
TEST_USER_PASSWORD = os.getenv('TEST_USER_PASSWORD', 'LoadTest2026!')
MISTRAL_MAX_CONCURRENT = int(os.getenv('MISTRAL_MAX_CONCURRENT', '5'))  # Low for 3 free keys at ~1 req/s each
MISTRAL_MAX_PER_MINUTE = int(os.getenv('MISTRAL_MAX_PER_MINUTE', '15'))  # ~5/min per key
ENABLE_ML_TRAINING = os.getenv('ENABLE_ML_TRAINING', 'true').lower() == 'true'
MAX_ML_TRAINING_RUNS = int(os.getenv('MAX_ML_TRAINING_RUNS', '2'))
CACHE_HIT_DATASET_ID = os.getenv('CACHE_HIT_DATASET_ID', 'ds_3c334902')
CACHE_HIT_MODEL_TYPE = os.getenv('CACHE_HIT_MODEL_TYPE', 'RandomForestClassifier')
CACHE_MISS_DATASET_ID = os.getenv('CACHE_MISS_DATASET_ID', 'ds_b28e58be')
CACHE_MISS_MODEL_TYPE = os.getenv('CACHE_MISS_MODEL_TYPE', 'LogisticRegression')
CACHE_MISS_TARGET_COLUMN = os.getenv('CACHE_MISS_TARGET_COLUMN', 'target')
SSE_TIMEOUT_SECONDS = int(os.getenv('SSE_TIMEOUT_SECONDS', '300'))
