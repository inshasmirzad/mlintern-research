#!/usr/bin/env python3
"""
Train a Random Forest classifier on the Breast Cancer Wisconsin dataset.
"""

from sklearn.datasets import load_breast_cancer
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
import sys
import os

def main():
    # Debugging prints
    print("Python executable:", sys.executable, file=sys.stderr)
    print("Current working directory:", os.getcwd(), file=sys.stderr)
    
    # Load dataset
    print("Loading dataset...", file=sys.stderr)
    data = load_breast_cancer()
    X, y = data.data, data.target
    
    # Split dataset
    print("Splitting dataset...", file=sys.stderr)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    # Train model
    print("Training model...", file=sys.stderr)
    model = RandomForestClassifier(n_estimators=100, random_state=42)
    model.fit(X_train, y_train)
    
    # Evaluate
    print("Evaluating model...", file=sys.stderr)
    predictions = model.predict(X_test)
    accuracy = accuracy_score(y_test, predictions)
    
    print(f"Accuracy: {accuracy:.4f}")

if __name__ == "__main__":
    main()