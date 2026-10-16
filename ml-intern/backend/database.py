import os
import logging
import certifi
from pymongo import AsyncMongoClient

logger = logging.getLogger(__name__)

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = os.environ.get("MONGO_DB_NAME", "ml_intern")

class Database:
    client: AsyncMongoClient = None
    db = None

    @classmethod
    def connect_db(cls):
        if cls.client is None:
            # Mask the URI to avoid printing credentials
            masked_uri = MONGO_URI
            if "@" in masked_uri:
                parts = masked_uri.split("@")
                masked_uri = "mongodb+srv://***:***@" + parts[1]
            logger.info(f"Connecting to MongoDB at {masked_uri}...")
            kwargs = {"maxPoolSize": 2000}
            if "+srv" in MONGO_URI:
                kwargs["tlsCAFile"] = certifi.where()
            cls.client = AsyncMongoClient(MONGO_URI, **kwargs)
            cls.db = cls.client[DB_NAME]
            logger.info("Connected to MongoDB successfully.")

    @classmethod
    def get_db(cls):
        if cls.db is None:
            cls.connect_db()
        return cls.db

database = Database()

def get_db():
    return database.get_db()
