import os
import xgboost as xgb
import pandas as pd
from sklearn.model_selection import train_test_split

from app.services.bug_service import fetch_bug_dev_pairs, fetch_all_developers
from app.services.ltr_features import build_training_dataset, FEATURE_COLUMNS
from app.utils.ml_paths import get_ltr_model_path, get_ltr_dataset_path

from app.services.bug_service import _dbname


async def train_ltr_model(
    organization: str,
    project: str,
    force_retrain: bool = False,
):
    MODEL_PATH = get_ltr_model_path(organization, project)
    DATASET_PATH = get_ltr_dataset_path(organization, project)
    database = _dbname(organization, project)
    # 1) Cek apakah model sudah ada
    if os.path.exists(MODEL_PATH) and not force_retrain:
        return {
            "status": "skipped",
            "reason": "model_already_exists",
            "model_path": MODEL_PATH,
        }

    # 2) Ambil data dari Neo4j via bug_services
    bug_dev_pairs = await fetch_bug_dev_pairs(database)
    all_devs = await fetch_all_developers(database)

    if not bug_dev_pairs:
        return {"status": "failed", "reason": "no_bug_dev_pairs"}

    if not all_devs:
        return {"status": "failed", "reason": "no_developers"}

    # 3) Build training dataset
    df = build_training_dataset(bug_dev_pairs, all_devs)
    df.to_csv(DATASET_PATH, index=False)

    # butuh minimal bug untuk training LTR
    if df["bug_id"].nunique() < 5:
        return {
            "status": "failed",
            "reason": "not_enough_bugs_for_training",
            "num_bugs": int(df["bug_id"].nunique()),
        }

    # 4) Build X, y, group
    X = df[FEATURE_COLUMNS].values
    y = df["label"].values

    bug_ids = df["bug_id"].unique()
    train_bugs, test_bugs = train_test_split(bug_ids, test_size=0.2, random_state=42)

    train_df = df[df["bug_id"].isin(train_bugs)]
    test_df = df[df["bug_id"].isin(test_bugs)]

    X_train = train_df[FEATURE_COLUMNS].values
    y_train = train_df["label"].values
    group_train = train_df.groupby("bug_id").size().tolist()

    X_test = test_df[FEATURE_COLUMNS].values
    y_test = test_df["label"].values
    group_test = test_df.groupby("bug_id").size().tolist()

    # 5) Train model
    model = xgb.XGBRanker(
        n_estimators=300,
        learning_rate=0.1,
        max_depth=6,
        objective="rank:pairwise",
        subsample=0.8,
        colsample_bytree=0.8,
    )

    model.fit(
        X_train,
        y_train,
        group=group_train,
        eval_set=[(X_test, y_test)],
        eval_group=[group_test],
        verbose=True,
    )

    # 6) Save model
    model.save_model(MODEL_PATH)

    return {
        "status": "success",
        "model_path": MODEL_PATH,
        "dataset_path": DATASET_PATH,
        "num_training_bugs": int(len(train_bugs)),
        "num_test_bugs": int(len(test_bugs)),
        "rows": int(len(df)),
        "features": FEATURE_COLUMNS,
    }
