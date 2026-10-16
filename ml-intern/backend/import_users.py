import asyncio
import certifi
import json
from bson import json_util
from pymongo import AsyncMongoClient

MONGO_URI = "mongodb+srv://insha2125_db_user:TestPassword123@cluster0.bvh8uvg.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
DB_NAME = "ml_intern"

async def main():
    print("Connecting to database...")
    client = AsyncMongoClient(MONGO_URI, tlsCAFile=certifi.where())
    db = client[DB_NAME]
    
    try:
        with open("backup_users.json", "r") as f:
            data = json_util.loads(f.read())
    except FileNotFoundError:
        print("Error: backup_users.json not found. Did you run export_users.py first?")
        return
        
    # Re-insert users
    if data.get("users"):
        print(f"Restoring {len(data['users'])} users...")
        await db.users.insert_many(data["users"])
        
    # Re-insert interactions
    if data.get("user_interactions"):
        print(f"Restoring {len(data['user_interactions'])} interactions...")
        await db.user_interactions.insert_many(data["user_interactions"])
        
    # Re-insert sessions
    if data.get("sessions"):
        print(f"Restoring {len(data['sessions'])} sessions...")
        await db.sessions.insert_many(data["sessions"])
        
    print("\nRestore complete! 'abhinesh' and 'ibn' are safely back in the database.")

if __name__ == "__main__":
    asyncio.run(main())
