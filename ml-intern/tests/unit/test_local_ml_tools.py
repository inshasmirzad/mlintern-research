import pandas as pd

from agent.tools import local_ml_tools


def test_prepare_training_data_handles_categorical_columns():
    df = pd.DataFrame(
        {
            "age": [20, 30, 40],
            "city": ["NY", "LA", "NY"],
            "target": [0, 1, 0],
        }
    )

    X, y = local_ml_tools._prepare_training_data(df, "target")

    assert list(X.columns) == ["age", "city_LA", "city_NY"]
    assert y.tolist() == [0, 1, 0]
