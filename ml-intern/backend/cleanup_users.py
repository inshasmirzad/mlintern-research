import asyncio
import os
import certifi
from pymongo import AsyncMongoClient

MONGO_URI = "mongodb+srv://insha2125_db_user:TestPassword123@cluster0.bvh8uvg.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
DB_NAME = "ml_intern"

ALLOWED_USERNAMES = ["abhinesh", "ibn"]

async def main():
    print(f"Connecting to MongoDB: {DB_NAME}...")
    client = AsyncMongoClient(MONGO_URI, tlsCAFile=certifi.where())
    db = client[DB_NAME]
    
    # Get all users
    all_users = await db.users.find().to_list(length=None)
    
    allowed_user_ids = []
    users_to_delete = []
    
    print("\n--- User Audit ---")
    for user in all_users:
        if user.get("username") in ALLOWED_USERNAMES:
            print(f"KEEPING user: {user.get('username')} (id: {user.get('user_id')})")
            allowed_user_ids.append(user.get("user_id"))
        else:
            print(f"DELETING user: {user.get('username')} (id: {user.get('user_id')})")
            users_to_delete.append(user.get("user_id"))
            
    if not users_to_delete:
        print("\nNo users found to delete. Exiting.")
        return
        
    print(f"\nProceeding to delete {len(users_to_delete)} users and their associated data...")
    
    # 1. Delete users
    user_del_result = await db.users.delete_many({"user_id": {"$in": users_to_delete}})
    print(f"Deleted {user_del_result.deleted_count} users from 'users' collection.")
    
    # 2. Delete user interactions
    interaction_del_result = await db.user_interactions.delete_many({"user_id": {"$in": users_to_delete}})
    print(f"Deleted {interaction_del_result.deleted_count} interactions from 'user_interactions' collection.")
    
    # 3. Clean up other potential collections based on user_id (if they exist)
    collections = await db.list_collection_names()
    if "sessions" in collections:
        session_del_result = await db.sessions.delete_many({"user_id": {"$in": users_to_delete}})
        print(f"Deleted {session_del_result.deleted_count} sessions from 'sessions' collection.")
        
    print("\nCleanup complete! Only 'abhinesh' and 'ibn' remain.")

if __name__ == "__main__":
    asyncio.run(main())
