from typing import List, Dict, Any
import numpy as np
from app.utils.ml_paths import get_ltr_model_path

from app.services.ltr_model import load_ltr_model
from app.services.ltr_features import (
    FEATURE_COLUMNS,
    fetch_bug_context,
    fetch_candidate_developers,
    build_feature_row,
)
from app.services.bug_service import _dbname


async def recommend_developers_ltr(
    organization: str,
    project: str,
    bug_id: str,
    top_k: int = 5,
) -> Dict[str, Any]:
    """
    Inference LTR:
    - ambil konteks bug
    - ambil candidate dev
    - hitung fitur
    - predict skor
    - sort
    """
    
    database = _dbname(organization, project)
    bug_ctx = await fetch_bug_context(database=database, bug_id=bug_id)
    if not bug_ctx:
        return {"bug_id": bug_id, "recommended_developers": []}

    bug_topic_id = bug_ctx.get("topic_id")
    if bug_topic_id is None:
        # tidak ada topic → tidak bisa pakai fitur topic-match
        # kamu bisa fallback ke rule-based di sini
        return {"bug_id": bug_id, "recommended_developers": []}
    
    candidates = await fetch_candidate_developers(
        database=database,
        bug_topic_id=bug_topic_id,
    )

    if not candidates:
        return {"bug_id": bug_id, "recommended_developers": []}

    feature_rows: List[Dict[str, float]] = []
    meta_rows: List[Dict[str, Any]] = []

    for dev_ctx in candidates:
        feat, meta = build_feature_row(bug_ctx, dev_ctx)
        feature_rows.append(feat)
        meta_rows.append(meta)

    # Susun X sesuai urutan FEATURE_COLUMNS
    X = np.array([[row[col] for col in FEATURE_COLUMNS] for row in feature_rows])

    model = load_ltr_model(organization, project)
    scores = model.predict(X)

    # gabungkan meta + score
    recs = []
    for meta, score in zip(meta_rows, scores):
        item = {**meta, "score": float(score)}
        recs.append(item)

    # sort desc by score
    recs.sort(key=lambda x: x["score"], reverse=True)

    return {
        "bug_id": bug_id,
        "topic_id": bug_topic_id,
        "total_candidates": len(recs),
        "recommended_developers": recs[:top_k],
    }
