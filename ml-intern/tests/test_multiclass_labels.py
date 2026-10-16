"""Saved multiclass classifiers preserve the dataset's original class labels."""

import pytest
from sklearn.datasets import load_iris
from sklearn.pipeline import Pipeline

from agent.tools.local_ml_tools import LabelEncodedClassifier, _prepare_training_data


def test_xgboost_multiclass_predictions_keep_string_labels() -> None:
    xgboost = pytest.importorskip("xgboost")
    frame = load_iris(as_frame=True).frame
    names = {0: "setosa", 1: "versicolor", 2: "virginica"}
    frame["target"] = frame["target"].map(names)
    features, labels = _prepare_training_data(frame, "target")
    model = LabelEncodedClassifier(
        Pipeline(
            [
                (
                    "estimator",
                    xgboost.XGBClassifier(n_estimators=5, n_jobs=1, random_state=42),
                ),
            ]
        )
    )
    model.fit(features, labels)
    predictions = model.predict(features.iloc[:10])
    assert set(predictions).issubset(set(names.values()))
    assert set(model.classes_) == set(names.values())
