#!/usr/bin/env python3
"""
Train a Random Forest classifier on Scikit-learn's built-in Breast Cancer dataset.
"""

from sklearn.datasets import load_breast_cancer
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score

def main():
    print("Loading dataset...")
    X, y = load_breast_cancer(return_X_y=True)
    print(f"Dataset loaded: {X.shape[0]} samples, {X.shape[1]} features.")
    
    print("Splitting data...")
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    print(f"Train size: {X_train.shape[0]}, Test size: {X_test.shape[0]}")
    
    print("Training Random Forest...")
    clf = RandomForestClassifier(random_state=42)
    clf.fit(X_train, y_train)
    print("Training completed.")
    
    print("Evaluating model...")
    y_pred = clf.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)
    print(f"Accuracy: {accuracy:.4f}")

if __name__ == "__main__":
    main()