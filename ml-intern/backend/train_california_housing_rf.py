#!/usr/bin/env python3
"""
Train a Random Forest regressor on the California Housing dataset.
Predict the price for a house with 2 rooms and report performance.
"""

from sklearn.datasets import fetch_california_housing
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import r2_score, mean_squared_error
import numpy as np

def main():
    print("Loading dataset...")
    X, y = fetch_california_housing(return_X_y=True)
    print(f"Dataset loaded: {X.shape[0]} samples, {X.shape[1]} features.")
    
    print("Splitting data...")
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    print(f"Train size: {X_train.shape[0]}, Test size: {X_test.shape[0]}")
    
    print("Training Random Forest regressor...")
    reg = RandomForestRegressor(random_state=42)
    reg.fit(X_train, y_train)
    print("Training completed.")
    
    print("Evaluating model...")
    y_pred = reg.predict(X_test)
    r2 = r2_score(y_test, y_pred)
    rmse = np.sqrt(mean_squared_error(y_test, y_pred))
    print(f"R² Score: {r2:.4f}")
    print(f"RMSE: {rmse:.4f}")
    
    # Predict price for a house with 2 rooms (AveRooms = 2)
    # Use median values for other features to avoid bias
    median_values = np.median(X_train, axis=0)
    input_features = median_values.copy()
    input_features[3] = 2  # Set AveRooms = 2
    
    predicted_price = reg.predict([input_features])[0]
    print(f"Predicted median house price for 2 rooms: ${predicted_price * 100000:,.2f}")

if __name__ == "__main__":
    main()