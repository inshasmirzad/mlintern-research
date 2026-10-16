import os
import argparse
from collections import defaultdict
from dotenv import load_dotenv
from pymongo import MongoClient
import certifi
import gridfs
from bson import ObjectId

# Load .env
load_dotenv("/Users/mathewbijugeorge/Downloads/ml-intern-main/.env")

def main():
    parser = argparse.ArgumentParser(description="Cleanup duplicate models")
    parser.add_argument("--dry-run", action="store_true", help="Run without deleting")
    args = parser.parse_args()

    mongo_uri = os.environ.get("MONGO_URI")
    db_name = os.environ.get("MONGO_DB_NAME", "ml_intern")

    if not mongo_uri:
        print("MONGO_URI not found in .env")
        return

    client = MongoClient(mongo_uri, tlsCAFile=certifi.where())
    db = client[db_name]
    models_coll = db.models
    fs = gridfs.GridFS(db)

    print(f"Connected to db: {db_name}")

    # Group models by (dataset_id, name)
    models = list(models_coll.find({}))
    groups = defaultdict(list)
    for model in models:
        # group by dataset_id, name
        group_key = (model.get("dataset_id"), model.get("name"))
        groups[group_key].append(model)

    print(f"Found {len(models)} total models across {len(groups)} unique groups.")

    to_keep = []
    to_delete = []

    for group_key, group_models in groups.items():
        if len(group_models) > 1:
            # Sort by created_at descending (latest first)
            group_models.sort(key=lambda x: x.get("created_at") or "", reverse=True)
            to_keep.append(group_models[0])
            to_delete.extend(group_models[1:])
        else:
            to_keep.append(group_models[0])

    print("\n--- Dry Run Report ---" if args.dry_run else "\n--- Execution Report ---")
    print(f"Models to keep: {len(to_keep)}")
    print(f"Models to delete: {len(to_delete)}")

    if to_delete:
        print("\nDetails of models to delete:")
        for model in to_delete:
            print(f"- Deleting model '{model.get('name')}' (ID: {model.get('model_id')}, Created: {model.get('created_at')})")
            if not args.dry_run:
                models_coll.delete_one({"_id": model["_id"]})
                gridfs_id = model.get("gridfs_file_id")
                if gridfs_id:
                    try:
                        fs.delete(ObjectId(gridfs_id) if isinstance(gridfs_id, str) else gridfs_id)
                    except Exception as e:
                        print(f"  Warning: failed to delete gridfs file {gridfs_id}: {e}")
        
        if not args.dry_run:
            print("\nSuccessfully deleted duplicate models and their GridFS files.")
        else:
            print("\nDry run complete. No models were actually deleted.")
    else:
        print("\nNo duplicate models found.")

if __name__ == "__main__":
    main()
