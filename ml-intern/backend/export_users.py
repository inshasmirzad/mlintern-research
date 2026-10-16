import asyncio
import certifi
import json
from bson import json_util
from pymongo import AsyncMongoClient

MONGO_URI = "mongodb+srv://insha2125_db_user:TestPassword123@cluster0.bvh8uvg.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
DB_NAME = "ml_intern"
ALLOWED_USERNAMES = ["abhinesh", "ibn"]

async def main():
    print("Connecting to database...")
    client = AsyncMongoClient(MONGO_URI, tlsCAFile=certifi.where())
    db = client[DB_NAME]
    
    # Export Users
    print("Exporting targeted users...")
    users_cursor = db.users.find({"username": {"$in": ALLOWED_USERNAMES}}, {"_id": 0})
    users_data = await users_cursor.to_list(length=None)
    
    user_ids = [u.get("user_id") for u in users_data]
    print(f"Found {len(users_data)} users to keep: {user_ids}")
    
    # Export Interactions
    print("Exporting their interactions...")
    interactions_cursor = db.user_interactions.find({"user_id": {"$in": user_ids}}, {"_id": 0})
    interactions_data = await interactions_cursor.to_list(length=None)
    print(f"Found {len(interactions_data)} interactions.")
    
    # Export Sessions
    sessions_data = []
    collections = await db.list_collection_names()
    if "sessions" in collections:
        print("Exporting their sessions...")
        sessions_cursor = db.sessions.find({"user_id": {"$in": user_ids}}, {"_id": 0})
        sessions_data = await sessions_cursor.to_list(length=None)
        print(f"Found {len(sessions_data)} sessions.")
    
    export_payload = {
        "users": users_data,
        "user_interactions": interactions_data,
        "sessions": sessions_data
    }
    
    with open("backup_users.json", "w") as f:
        f.write(json_util.dumps(export_payload, indent=2))
        
    print("\nData exported successfully to 'backup_users.json'!")

if __name__ == "__main__":
    asyncio.run(main())
