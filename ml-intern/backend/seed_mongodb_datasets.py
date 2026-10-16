import os
import io
import time
import uuid
import certifi
from dotenv import load_dotenv
from pymongo import MongoClient
import gridfs
import pandas as pd
from sklearn.datasets import load_iris, load_breast_cancer, fetch_california_housing

def seed_datasets():
    # Load .env variables
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
    
    mongo_uri = os.environ.get("MONGO_URI")
    db_name = os.environ.get("MONGO_DB_NAME", "ml_intern")
    
    if not mongo_uri:
        print("Error: MONGO_URI not found in .env")
        return

    print("Connecting to MongoDB...")
    kwargs = {}
    if "+srv" in mongo_uri:
        kwargs["tlsCAFile"] = certifi.where()
    client = MongoClient(mongo_uri, **kwargs)
    db = client[db_name]
    fs = gridfs.GridFS(db)
    
    datasets_to_load = [
        {
            "name": "Iris Species",
            "description": "The famous Iris database. A small dataset for classifying 3 species of iris flowers based on sepal and petal dimensions.",
            "task_type": "classification",
            "loader": load_iris
        },
        {
            "name": "Breast Cancer Wisconsin (Diagnostic)",
            "description": "Features are computed from digitized images of fine needle aspirates of breast masses. Used to classify tumors as malignant or benign.",
            "task_type": "binary_classification",
            "loader": load_breast_cancer
        },
        {
            "name": "California Housing",
            "description": "Median house prices for California districts derived from the 1990 census. Used for predicting house prices.",
            "task_type": "regression",
            "loader": fetch_california_housing
        }
    ]
    
    for meta in datasets_to_load:
        print(f"\nProcessing {meta['name']}...")
        
        # 1. Download data via sklearn
        data = meta["loader"](as_frame=True)
        df = data.frame
        
        # 2. Convert DataFrame to CSV in memory
        csv_buffer = io.StringIO()
        df.to_csv(csv_buffer, index=False)
        csv_bytes = csv_buffer.getvalue().encode('utf-8')
        
        # 3. Store raw CSV in GridFS
        file_id = fs.put(
            csv_bytes, 
            filename=f"{meta['name'].replace(' ', '_').lower()}.csv",
            content_type="text/csv"
        )
        print(f"  -> Uploaded raw CSV to GridFS with file_id: {file_id}")
        
        # 4. Save metadata in 'datasets' collection
        dataset_id = f"ds_{uuid.uuid4().hex[:8]}"
        dataset_doc = {
            "dataset_id": dataset_id,
            "name": meta["name"],
            "description": meta["description"],
            "task_type": meta["task_type"],
            "gridfs_file_id": str(file_id),
            "created_at": time.time()
        }
        
        db.datasets.insert_one(dataset_doc)
        print(f"  -> Saved metadata to 'datasets' collection with dataset_id: {dataset_id}")

    print("\n✅ Successfully seeded all datasets into MongoDB!")

if __name__ == "__main__":
    seed_datasets()
