from functools import lru_cache
import xgboost as xgb
from app.utils.ml_paths import get_ltr_model_path


@lru_cache(maxsize=32)
def load_ltr_model(organization: str, project: str):
    MODEL_PATH = get_ltr_model_path(organization, project)

    model = xgb.XGBRanker()
    model.load_model(MODEL_PATH)
    return model
