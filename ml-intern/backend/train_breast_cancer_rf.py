#!/usr/bin/env python3
"""
Train a Random Forest classifier on the Breast Cancer Wisconsin dataset.
Logs intermediate steps for debugging.
"""

import pickle
import numpy as np
from pymongo import MongoClient
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
import sys

def main():
    print("Starting script...")
    
    # Connect to MongoDB
    try:
        print("Connecting to MongoDB...")
        client = MongoClient('mongodb://localhost:27017/')
        db = client['ml_ecosystem']
        collection = db['datasets']
        print("MongoDB connected successfully.")
    except Exception as e:
        print(f"MongoDB connection failed: {e}")
        sys.exit(1)
    
    # Fetch dataset
    try:
        print("Fetching dataset...")
        dataset = collection.find_one({'dataset_id': 'ds_5b8b6bed'})
        if not dataset:
            print("Dataset not found.")
            sys.exit(1)
        print("Dataset fetched successfully.")
    except Exception as e:
        print(f"Failed to fetch dataset: {e}")
        sys.exit(1)
    
    # Load data
    try:
        print("Loading data...")
        data = pickle.loads(dataset['data'])
        X = data['features']
        y = data['target']
        print(f"Data loaded: {X.shape[0]} samples, {X.shape[1]} features.")
    except Exception as e:
        print(f"Failed to load data: {e}")
        sys.exit(1)
    
    # Split data
    try:
        print("Splitting data...")
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
        print(f"Train size: {X_train.shape[0]}, Test size: {X_test.shape[0]}")
    except Exception as e:
        print(f"Failed to split data: {e}")
        sys.exit(1)
    
    # Train Random Forest
    try:
        print("Training Random Forest...")
        clf = RandomForestClassifier(random_state=42)
        clf.fit(X_train, y_train)
        print("Training completed.")
    except Exception as e:
        print(f"Failed to train model: {e}")
        sys.exit(1)
    
    # Evaluate
    try:
        print("Evaluating model...")
        y_pred = clf.predict(X_test)
        accuracy = accuracy_score(y_test, y_pred)
        print(f"Accuracy: {accuracy:.4f}")
    except Exception as e:
        print(f"Failed to evaluate model: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()