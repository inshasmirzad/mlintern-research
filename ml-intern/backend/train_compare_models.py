#!/usr/bin/env python3
"""
Train a Random Forest classifier and an SVM on the Breast Cancer Wisconsin dataset.
Compare their accuracies and save the best-performing model.
"""

from sklearn.datasets import load_breast_cancer
from sklearn.ensemble import RandomForestClassifier
from sklearn.svm import SVC
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
import joblib
import os
import sys

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
    
    # Train Random Forest
    print("Training Random Forest...", file=sys.stderr)
    rf_model = RandomForestClassifier(n_estimators=100, random_state=42)
    rf_model.fit(X_train, y_train)
    rf_predictions = rf_model.predict(X_test)
    rf_accuracy = accuracy_score(y_test, rf_predictions)
    
    # Train SVM
    print("Training SVM...", file=sys.stderr)
    svm_model = SVC(kernel='linear', random_state=42)
    svm_model.fit(X_train, y_train)
    svm_predictions = svm_model.predict(X_test)
    svm_accuracy = accuracy_score(y_test, svm_predictions)
    
    # Compare accuracies
    print(f"Random Forest Accuracy: {rf_accuracy:.4f}", file=sys.stderr)
    print(f"SVM Accuracy: {svm_accuracy:.4f}", file=sys.stderr)
    
    # Save the best model
    if rf_accuracy >= svm_accuracy:
        best_model = rf_model
        best_model_name = "Random Forest"
        best_accuracy = rf_accuracy
        model_path = 'breast_cancer_rf.pkl'
    else:
        best_model = svm_model
        best_model_name = "SVM"
        best_accuracy = svm_accuracy
        model_path = 'breast_cancer_svm.pkl'
    
    joblib.dump(best_model, model_path)
    print(f"Best model ({best_model_name}) saved to: {os.path.abspath(model_path)}", file=sys.stderr)
    print(f"Best Accuracy: {best_accuracy:.4f}")
    print(f"Best Model: {best_model_name}")

if __name__ == "__main__":
    main()