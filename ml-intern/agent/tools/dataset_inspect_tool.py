"""
Dataset Inspection Tool — Download/inspect local datasets from MongoDB GridFS.
"""
import json
import io
import asyncio
from typing import Any
import pandas as pd
from bson.objectid import ObjectId
from gridfs import AsyncGridFSBucket

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent / "backend"))
from database import get_db

DATASET_INSPECT_TOOL_SPEC = {
    "name": "dataset_inspect",
    "description": "Inspect a local dataset by passing its MongoDB dataset_id.",
    "parameters": {
        "type": "object",
        "properties": {
            "dataset_id": {
                "type": "string",
                "description": "The dataset_id (e.g. ds_abc123) from the list_local_datasets tool",
            },
            "sample_rows": {
                "type": "integer",
                "description": "Number of rows to sample",
                "default": 3,
            }
        },
        "required": ["dataset_id"],
    },
}

async def dataset_inspect_handler(arguments: dict[str, Any], **kwargs) -> tuple[str, bool]:
    dataset_id = arguments.get("dataset_id")
    sample_rows = arguments.get("sample_rows", 3)
    
    if not dataset_id:
        return "dataset_id is required.", False
        
    try:
        db = get_db()
        dataset_record = await db.datasets.find_one({"dataset_id": dataset_id})
        
        if not dataset_record:
            return f"Dataset not found in MongoDB with ID: {dataset_id}", False
            
        gridfs_file_id_str = dataset_record.get("gridfs_file_id")
        if not gridfs_file_id_str:
            return f"Dataset {dataset_id} does not have a gridfs_file_id.", False
            
        fs = AsyncGridFSBucket(db)
        
        # Read file from GridFS
        file_io = io.BytesIO()
        await fs.download_to_stream(ObjectId(gridfs_file_id_str), file_io)
        file_bytes = file_io.getvalue()
        
        file_name = dataset_record.get("name", "").lower()
        
        bytes_io = io.BytesIO(file_bytes)
        
        if file_name.endswith('.csv'):
            df = pd.read_csv(bytes_io, nrows=sample_rows + 1)
        elif file_name.endswith('.json') or file_name.endswith('.jsonl'):
            df = pd.read_json(bytes_io, lines=True, nrows=sample_rows + 1)
        elif file_name.endswith('.parquet'):
            df = pd.read_parquet(bytes_io).head(sample_rows + 1)
        else:
            # Fallback to CSV if extension is unknown
            df = pd.read_csv(bytes_io, nrows=sample_rows + 1)
            
        columns = df.columns.tolist()
        sample = df.head(sample_rows).to_dict(orient='records')
        
        result = f"Columns: {columns}\nSample Data:\n{json.dumps(sample, indent=2)}"
        return result, True
    except Exception as e:
        return f"Error reading dataset from MongoDB: {str(e)}", False
