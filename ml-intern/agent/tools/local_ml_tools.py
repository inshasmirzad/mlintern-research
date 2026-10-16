import asyncio
import json
import os
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import pandas as pd
from gridfs import AsyncGridFSBucket

sys.path.append(str(Path(__file__).parent.parent.parent / "backend"))
try:
    from backend.database import get_db
except ImportError:  # pragma: no cover - fallback for direct script execution
    from database import get_db

import logging

logger = logging.getLogger(__name__)

# Bound local CPU work so chat sessions can remain responsive while training.
_train_slots = asyncio.Semaphore(
    max(1, int(os.environ.get("ML_TRAIN_MAX_CONCURRENT", "2")))
)
SUPPORTED_TRAIN_MODELS = {
    "RandomForestClassifier",
    "LogisticRegression",
    "XGBClassifier",
    "RandomForestRegressor",
    "LinearRegression",
    "XGBRegressor",
}


class LabelEncodedClassifier:
    """Fit classifiers on integer labels and return the dataset's original labels."""

    def __init__(self, estimator: Any) -> None:
        self.estimator = estimator

    def fit(
        self, features: pd.DataFrame, labels: pd.Series
    ) -> "LabelEncodedClassifier":
        from sklearn.preprocessing import LabelEncoder

        self.label_encoder = LabelEncoder()
        encoded = self.label_encoder.fit_transform(labels)
        self.estimator.fit(features, encoded)
        self.classes_ = self.label_encoder.classes_
        return self

    def predict(self, features: pd.DataFrame) -> Any:
        encoded = self.estimator.predict(features)
        return self.label_encoder.inverse_transform(encoded)

    def predict_proba(self, features: pd.DataFrame) -> Any:
        return self.estimator.predict_proba(features)


def _redact_payload(data: Any, max_list_items=5) -> Any:
    """Redact sensitive keys and truncate large lists/dataframes for safe logging."""
    if isinstance(data, dict):
        result = {}
        for k, v in data.items():
            if any(
                sensitive in k.lower()
                for sensitive in ["key", "token", "secret", "password"]
            ):
                result[k] = "***REDACTED***"
            else:
                result[k] = _redact_payload(v, max_list_items)
        return result
    elif isinstance(data, list):
        if len(data) > max_list_items:
            return [
                _redact_payload(i, max_list_items) for i in data[:max_list_items]
            ] + [f"... truncated {len(data) - max_list_items} items"]
        return [_redact_payload(i, max_list_items) for i in data]
    elif hasattr(data, "shape") and hasattr(data, "head"):  # DataFrame
        return f"DataFrame(shape={data.shape}, head=\n{data.head(2).to_dict()})"
    elif isinstance(data, str) and len(data) > 500:
        return data[:500] + f"... truncated {len(data) - 500} chars"
    return data


# ---------------------------------------------------------
# LIST LOCAL DATASETS
# ---------------------------------------------------------

LIST_LOCAL_DATASETS_TOOL_SPEC = {
    "name": "list_local_datasets",
    "description": (
        "Retrieve a list of available local datasets managed in our MongoDB database. "
        "CRITICAL POLICY: This is the ONLY tool you are allowed to use to find datasets. "
        "You MUST NOT search the internet (Kaggle, GitHub, etc.) for datasets. If a requested dataset is not in this list, inform the user you are restricted to local datasets."
    ),
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


async def list_local_datasets_handler(
    arguments: dict[str, Any], session: Any = None
) -> tuple[str, bool]:
    try:
        db = get_db()
        cursor = db.datasets.find().sort("created_at", -1)
        datasets = await cursor.to_list(length=100)

        if not datasets:
            return "No local datasets found.", True

        lines = ["## Available Local Datasets\n"]
        for ds in datasets:
            lines.append(
                f"- **ID:** {ds.get('dataset_id', ds.get('id', ds.get('_id')))}"
            )
            lines.append(f"  **Name:** {ds.get('name')}")
            lines.append(f"  **Task Type:** {ds.get('task_type')}")
            lines.append(f"  **Description:** {ds.get('description')}\n")

        return "\n".join(lines), True
    except Exception as e:
        return f"Error listing datasets: {e}", False


# ---------------------------------------------------------
# SAVE DATASET METADATA
# ---------------------------------------------------------

SAVE_DATASET_METADATA_TOOL_SPEC = {
    "name": "save_dataset_metadata",
    "description": (
        "Permanently register a new dataset into the local database (MongoDB datasets collection). "
        "Use this tool when you have discovered a great dataset online and want to save its metadata "
        "locally so it can be queried later."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "The name of the dataset (e.g. 'Titanic Survival', 'Movie Reviews').",
            },
            "description": {
                "type": "string",
                "description": "A comprehensive description of what the dataset contains, where it came from, and any links.",
            },
            "task_type": {
                "type": "string",
                "description": "The machine learning task this dataset is suited for (e.g. 'text-classification', 'regression', 'image-generation').",
            },
        },
        "required": ["name", "description", "task_type"],
    },
}


async def save_dataset_metadata_handler(
    arguments: dict[str, Any], session: Any = None
) -> tuple[str, bool]:
    try:
        name = arguments["name"]
        description = arguments["description"]
        task_type = arguments["task_type"]

        db = get_db()
        dataset_id = f"ds_{uuid.uuid4().hex[:8]}"

        await db.datasets.insert_one(
            {
                "dataset_id": dataset_id,
                "name": name,
                "description": description,
                "task_type": task_type,
                "created_at": time.time(),
            }
        )

        return f"Successfully saved dataset metadata! Dataset ID: {dataset_id}", True
    except Exception as e:
        return f"Error saving dataset metadata: {e}", False


# ---------------------------------------------------------
# LIST LOCAL MODELS
# ---------------------------------------------------------

LIST_LOCAL_MODELS_TOOL_SPEC = {
    "name": "list_local_models",
    "description": (
        "Retrieve a list of available local models. "
        "Use this ONLY to see what base models or fine-tuned models you have locally. "
        "To find NEW models online, use the `web_search` tool."
    ),
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


async def list_local_models_handler(
    arguments: dict[str, Any], session: Any = None
) -> tuple[str, bool]:
    try:
        db = get_db()
        cursor = db.models.find().sort("created_at", -1)
        models = await cursor.to_list(length=100)

        lines = [
            "## Supported training algorithms",
            "Classification: XGBClassifier, RandomForestClassifier, LogisticRegression",
            "Regression: XGBRegressor, RandomForestRegressor, LinearRegression",
            "XGBoost requires the optional xgboost dependency.",
            "",
            "## Saved local models",
        ]
        if not models:
            return "\n".join(lines + ["No saved models yet."]), True
        for mod in models:
            lines.append(
                f"- **ID:** {mod.get('model_id', mod.get('id', mod.get('_id')))}"
            )
            lines.append(f"  **Name:** {mod.get('name')}")
            lines.append(f"  **Base Model:** {mod.get('base_model')}")
            lines.append(f"  **Status:** {mod.get('status')}")
            if mod.get("dataset_id"):
                lines.append(f"  **Trained on Dataset:** {mod['dataset_id']}")
            if mod.get("metrics"):
                try:
                    metrics = (
                        mod["metrics"]
                        if isinstance(mod["metrics"], dict)
                        else json.loads(mod["metrics"])
                    )
                    if metrics:
                        lines.append(f"  **Metrics:** {metrics}")
                except (TypeError, ValueError):
                    logger.debug(
                        "Skipping malformed metrics for model %s", mod.get("model_id")
                    )
            lines.append("")

        return "\n".join(lines), True
    except Exception as e:
        return f"Error listing models: {e}", False


# ---------------------------------------------------------
# SAVE LOCAL MODEL
# ---------------------------------------------------------

SAVE_LOCAL_MODEL_TOOL_SPEC = {
    "name": "save_local_model",
    "description": (
        "Permanently save a trained model artifact (.pkl, .h5, etc.) into MongoDB GridFS and register its metadata. "
        "You MUST use this tool immediately after successfully training a model locally."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "model_path": {
                "type": "string",
                "description": "Absolute path to the local model file on disk (e.g. '/tmp/my_model.pkl').",
            },
            "name": {
                "type": "string",
                "description": "A descriptive name for the model (e.g. 'Random Forest Cancer Predictor').",
            },
            "dataset_id": {
                "type": "string",
                "description": "The dataset_id of the MongoDB dataset it was trained on (for lineage).",
            },
            "framework": {
                "type": "string",
                "description": "The framework used (e.g. 'scikit-learn', 'xgboost', 'pytorch').",
            },
            "metrics": {
                "type": "string",
                "description": "JSON string of evaluation metrics (e.g. '{\"accuracy\": 0.95}').",
            },
        },
        "required": ["model_path", "name", "dataset_id", "framework"],
    },
}


async def save_local_model_handler(
    arguments: dict[str, Any], session: Any = None
) -> tuple[str, bool]:
    model_path = arguments["model_path"]
    name = arguments["name"]
    dataset_id = arguments["dataset_id"]
    framework = arguments.get("framework", "unknown")
    metrics_str = arguments.get("metrics", "{}")

    if not os.path.exists(model_path):
        return f"File not found: {model_path}", False

    try:
        metrics = (
            json.loads(metrics_str) if isinstance(metrics_str, str) else metrics_str
        )
    except Exception:
        metrics = {}

    try:
        db = get_db()
        fs = AsyncGridFSBucket(db)

        # Read the file and upload to GridFS
        file_bytes = await asyncio.to_thread(Path(model_path).read_bytes)

        file_id = await fs.upload_from_stream(os.path.basename(model_path), file_bytes)

        new_id = f"mod_{uuid.uuid4().hex[:8]}"

        record = {
            "model_id": new_id,
            "name": name,
            "gridfs_file_id": str(file_id),
            "dataset_id": dataset_id,
            "framework": framework,
            "status": "ready",
            "metrics": metrics,
            "created_at": time.time(),
        }
        for key in (
            "model_type",
            "target_column",
            "task_type",
            "run_id",
            "feature_columns",
            "class_labels",
        ):
            if arguments.get(key) is not None:
                record[key] = arguments[key]
        await db.models.insert_one(record)

        return (
            f"Successfully uploaded model to GridFS and registered metadata! Model ID: {new_id}",
            True,
        )
    except Exception as e:
        return f"Error saving model: {e}", False


# ---------------------------------------------------------
# TRAIN LOCAL MODEL
# ---------------------------------------------------------

TRAIN_LOCAL_MODEL_TOOL_SPEC = {
    "name": "train_local_model",
    "description": (
        "Train a standard machine learning model on a local dataset stored in MongoDB. "
        "The model is trained natively in the agent process and automatically saved. "
        "It reuses an existing model by default. Set force_retrain=true only when the "
        "user explicitly needs a distinct new model; provide a unique run_id for research runs. "
        "Supported models include XGBClassifier and XGBRegressor."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "dataset_id": {
                "type": "string",
                "description": "The dataset_id of the dataset to train on (e.g., 'ds_abc123').",
            },
            "model_type": {
                "type": "string",
                "description": "Type of model to train (e.g., 'RandomForestRegressor', 'LinearRegression', 'RandomForestClassifier', 'LogisticRegression').",
            },
            "target_column": {
                "type": "string",
                "description": "The name of the target column to predict.",
            },
            "force_retrain": {
                "type": "boolean",
                "description": "Create a fresh model instead of reusing a cached one. Defaults to false.",
            },
            "run_id": {
                "type": "string",
                "description": "Unique research request ID, used to verify one saved model per request.",
            },
        },
        "required": ["dataset_id", "model_type", "target_column"],
    },
}


def _prepare_training_data(
    df: pd.DataFrame, target_column: str
) -> tuple[pd.DataFrame, pd.Series]:
    if target_column not in df.columns:
        raise KeyError(f"Target column '{target_column}' not found in dataset")

    prepared = df.copy()
    prepared = prepared.dropna(subset=[target_column]).copy()

    X = prepared.drop(columns=[target_column])
    y = prepared[target_column]

    if X.empty:
        raise ValueError(
            "No feature columns available after removing the target column"
        )

    return X, y


async def train_local_model_handler(
    arguments: dict[str, Any], session: Any = None
) -> tuple[str, bool]:
    dataset_id = arguments.get("dataset_id")
    model_type = arguments.get("model_type")
    target_column = arguments.get("target_column")
    force_retrain = arguments.get("force_retrain", False) is True
    run_id = arguments.get("run_id")

    logger.info(
        f"Starting train_local_model_handler with args: {_redact_payload(arguments)}"
    )

    try:
        if model_type not in SUPPORTED_TRAIN_MODELS:
            return (
                f"Model type '{model_type}' is not supported. Choose from {sorted(SUPPORTED_TRAIN_MODELS)}.",
                False,
            )
        if run_id is not None and (
            not isinstance(run_id, str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", run_id)
        ):
            return (
                "run_id must contain 1–80 letters, numbers, underscores or hyphens.",
                False,
            )
        # Before training, check if an identical model already exists
        db = get_db()
        existing_model = None
        if run_id:
            existing_model = await db.models.find_one(
                {"run_id": run_id, "status": "ready"}
            )
            if existing_model and any(
                existing_model.get(key) != value
                for key, value in (
                    ("dataset_id", dataset_id),
                    ("model_type", model_type),
                    ("target_column", target_column),
                )
            ):
                return "run_id already belongs to a different saved model.", False
        if not force_retrain and not run_id and existing_model is None:
            existing_model = await db.models.find_one(
                {
                    "dataset_id": dataset_id,
                    "name": {
                        "$regex": f"^{re.escape(model_type)} on ",
                        "$options": "i",
                    },
                    "status": "ready",
                },
                sort=[("created_at", -1)],
            )

        if existing_model:
            metrics = existing_model.get("metrics", {})
            model_id = existing_model.get("model_id", "unknown")
            logger.info(
                f"Cache HIT: Found existing {model_type} for dataset {dataset_id} -> {model_id}"
            )
            result = [
                "✅ Cache HIT: Found existing trained model!",
                f"Model ID: {model_id}",
                f"Name: {existing_model.get('name', 'N/A')}",
                f"Framework: {existing_model.get('framework', 'N/A')}",
                f"Metrics: {json.dumps(metrics, indent=2) if isinstance(metrics, dict) else metrics}",
                "",
                f"This model was previously trained on dataset {dataset_id}.",
                "No retraining was necessary.",
            ]
            return "\n".join(result), True

        logger.info(
            f"Cache MISS: No existing {model_type} for dataset {dataset_id}, proceeding with training"
        )

        # 1. Load Dataset from MongoDB
        logger.info(f"Step 1: Loading dataset {dataset_id} from MongoDB")
        dataset_record = await db.datasets.find_one({"dataset_id": dataset_id})

        if not dataset_record:
            return f"Dataset not found in MongoDB with ID: {dataset_id}", False

        is_regression = (
            model_type.endswith("Regressor") or model_type == "LinearRegression"
        )
        dataset_task = dataset_record.get("task_type")
        if dataset_task == "regression" and not is_regression:
            return "This regression dataset needs a regressor model.", False
        if (
            dataset_task
            in {"classification", "binary_classification", "multiclass_classification"}
            and is_regression
        ):
            return "This classification dataset needs a classifier model.", False

        gridfs_file_id_str = dataset_record.get("gridfs_file_id")
        if not gridfs_file_id_str:
            return f"Dataset {dataset_id} does not have a gridfs_file_id.", False

        import io

        import pandas as pd
        from bson.objectid import ObjectId
        from gridfs import AsyncGridFSBucket

        fs = AsyncGridFSBucket(db)
        file_io = io.BytesIO()
        await fs.download_to_stream(ObjectId(gridfs_file_id_str), file_io)
        file_bytes = file_io.getvalue()

        file_name = dataset_record.get("name", "").lower()
        ds_name_formal = dataset_record.get("name", "Unknown Dataset")
        bytes_io = io.BytesIO(file_bytes)

        if file_name.endswith(".csv"):
            df = pd.read_csv(bytes_io)
        elif file_name.endswith((".json", ".jsonl")):
            df = pd.read_json(bytes_io, lines=True)
        elif file_name.endswith(".parquet"):
            df = pd.read_parquet(bytes_io)
        else:
            df = pd.read_csv(bytes_io)

        if target_column not in df.columns:
            return (
                f"Target column '{target_column}' not found in dataset. Available columns: {df.columns.tolist()}",
                False,
            )

        if is_regression and not pd.api.types.is_numeric_dtype(df[target_column]):
            return "Regression requires a numeric target column.", False

        X, y = await asyncio.to_thread(_prepare_training_data, df, target_column)

        if X.empty or X.shape[1] == 0:
            return (
                "No usable feature columns remained after preprocessing the dataset.",
                False,
            )

        # Determine task type automatically based on the model chosen
        from sklearn.compose import ColumnTransformer
        from sklearn.impute import SimpleImputer
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import OneHotEncoder

        numeric_columns = X.select_dtypes(include="number").columns.tolist()
        categorical_columns = [
            column for column in X.columns if column not in numeric_columns
        ]
        transformers = []
        if numeric_columns:
            transformers.append(
                ("numeric", SimpleImputer(strategy="median"), numeric_columns)
            )
        if categorical_columns:
            transformers.append(
                (
                    "categorical",
                    Pipeline(
                        [
                            ("impute", SimpleImputer(strategy="most_frequent")),
                            ("encode", OneHotEncoder(handle_unknown="ignore")),
                        ]
                    ),
                    categorical_columns,
                )
            )
        preprocessing = ColumnTransformer(transformers)

        from sklearn.model_selection import train_test_split

        counts = y.value_counts() if not is_regression else None
        stratify = (
            y
            if counts is not None
            and counts.min() >= 2
            and int(len(y) * 0.2) >= len(counts)
            else None
        )
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=stratify
        )

        # 2. Select and Train Model
        logger.info(
            f"Step 2: Selecting and training model {model_type} on X_shape={X.shape}"
        )
        model = None
        if "RandomForestRegressor" in model_type:
            from sklearn.ensemble import RandomForestRegressor

            model = RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=1)
        elif "LinearRegression" in model_type:
            from sklearn.linear_model import LinearRegression

            model = LinearRegression()
        elif "RandomForestClassifier" in model_type:
            from sklearn.ensemble import RandomForestClassifier

            model = RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=1)
        elif "LogisticRegression" in model_type:
            from sklearn.linear_model import LogisticRegression

            model = LogisticRegression(max_iter=1000)
        elif model_type in {"XGBClassifier", "XGBRegressor"}:
            try:
                from xgboost import XGBClassifier, XGBRegressor
            except ImportError:
                return "XGBoost is not installed. Run `uv sync --extra xgboost`.", False
            model = (XGBRegressor if is_regression else XGBClassifier)(
                n_estimators=100,
                max_depth=5,
                learning_rate=0.1,
                tree_method="hist",
                n_jobs=1,
                random_state=42,
            )
        else:
            return f"Model type '{model_type}' is not supported yet.", False

        model = Pipeline([("preprocessing", preprocessing), ("estimator", model)])
        if not is_regression:
            model = LabelEncodedClassifier(model)

        async with _train_slots:
            model, predictions = await asyncio.to_thread(
                lambda: (model.fit(X_train, y_train), model.predict(X_test))
            )

        # 3. Evaluate Metrics
        logger.info("Step 3: Evaluating model metrics")
        metrics = {}
        if is_regression:
            import numpy as np
            from sklearn.metrics import (
                mean_absolute_error,
                mean_squared_error,
                r2_score,
            )

            metrics["rmse"] = float(np.sqrt(mean_squared_error(y_test, predictions)))
            metrics["mae"] = float(mean_absolute_error(y_test, predictions))
            metrics["r2"] = float(r2_score(y_test, predictions))
        else:
            from sklearn.metrics import (
                accuracy_score,
                balanced_accuracy_score,
                f1_score,
            )

            metrics["accuracy"] = float(accuracy_score(y_test, predictions))
            metrics["f1_score"] = float(
                f1_score(y_test, predictions, average="weighted")
            )
            metrics["f1_macro"] = float(f1_score(y_test, predictions, average="macro"))
            metrics["balanced_accuracy"] = float(
                balanced_accuracy_score(y_test, predictions)
            )
            metrics["classes"] = int(y.nunique())

        # 4. Save Model Locally and to DB
        logger.info("Step 4: Saving model to disk and GridFS")
        import pickle
        import tempfile

        tmp_dir = tempfile.gettempdir()
        model_path = os.path.join(tmp_dir, f"model_{uuid.uuid4().hex[:8]}.pkl")
        await asyncio.to_thread(
            lambda: Path(model_path).write_bytes(pickle.dumps(model))
        )

        # Reuse save_local_model logic
        save_args = {
            "model_path": model_path,
            "name": f"{model_type} on {ds_name_formal}",
            "dataset_id": dataset_id,
            "framework": "scikit-learn",
            "metrics": json.dumps(metrics),
            "model_type": model_type,
            "target_column": target_column,
            "task_type": "regression" if is_regression else "classification",
            "feature_columns": list(X.columns),
            "run_id": run_id,
        }
        if not is_regression:
            save_args["class_labels"] = model.classes_.tolist()
        try:
            save_msg, save_success = await save_local_model_handler(save_args, session)
        finally:
            await asyncio.to_thread(os.unlink, model_path)

        if not save_success:
            return (
                f"Model trained successfully but failed to save: {save_msg}\nMetrics: {metrics}",
                False,
            )

        logger.info(f"New model trained and saved for {dataset_id}/{model_type}")

        result = [
            f"Successfully trained {model_type} on {ds_name_formal}!",
            f"Metrics: {json.dumps(metrics, indent=2)}",
            f"Save Status: {save_msg}",
        ]
        result_str = "\n".join(result)
        logger.info(
            f"Finished train_local_model_handler. Result: {_redact_payload(result_str)}"
        )
        return result_str, True
    except Exception as e:
        import traceback

        err_msg = f"Error training model: {e}\n{traceback.format_exc()}"
        logger.error(f"train_local_model_handler failed: {err_msg}")
        return err_msg, False
