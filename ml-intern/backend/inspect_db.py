import asyncio
import os
import certifi
from pymongo import AsyncMongoClient

MONGO_URI = "mongodb+srv://insha2125_db_user:TestPassword123@cluster0.bvh8uvg.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
DB_NAME = "ml_intern"

async def main():
    client = AsyncMongoClient(MONGO_URI, tlsCAFile=certifi.where())
    db = client[DB_NAME]
    collections = await db.list_collection_names()
    print(f"Collections: {collections}")
    for coll in collections:
        count = await db[coll].count_documents({})
        print(f"Collection {coll} has {count} documents.")
        # Try to see if it has 'username' or 'user_id'
        sample = await db[coll].find_one()
        if sample:
            print(f"  Sample keys: {list(sample.keys())}")
            if 'username' in sample:
                print(f"  Sample username: {sample['username']}")
            if 'user_id' in sample:
                print(f"  Sample user_id: {sample['user_id']}")

if __name__ == "__main__":
    asyncio.run(main())
