from typing import List, Dict, Any
import numpy as np
from app.utils.ml_paths import get_ltr_model_path
from app.services.nlp_topic_service import get_nlp_topic_service


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


async def recommend_developers_ltr_from_description(
    organization: str,
    project: str,
    database: str,
    summary: str,
    component: str | None = None,
    top_k: int = 5,
) -> Dict[str, Any]:
    """
    Rekomendasi developer menggunakan LTR,
    input berupa teks deskripsi / summary bug (BUKAN bug_id).

    Langkah:
      1) Infer topic_id dari summary via NlpTopicService (LDA).
      2) Ambil candidate developers untuk topic tersebut.
      3) Hitung fitur LTR per (pseudo-bug, dev).
      4) Model LTR menghasilkan skor ranking.
    """

    summary = (summary or "").strip()
    if not summary:
        return {
            "summary": summary,
            "component": component,
            "topic_id": None,
            "recommended_developers": [],
            "reason": "empty_summary",
        }

    # 1) Infer topic dari teks bug dengan LDA (per database)
    nlp_service = get_nlp_topic_service()
    topic_info = nlp_service.infer_topics(db_name=database, text=summary)

    main_topic_id = topic_info.get("main_topic_id")
    main_topic_prob = topic_info.get("main_topic_prob")

    if main_topic_id is None:
        return {
            "summary": summary,
            "component": component,
            "topic_id": None,
            "recommended_developers": [],
            "reason": "topic_inference_failed",
        }

    # 2) Ambil candidate developers berdasarkan topic dari Neo4j
    candidates = await fetch_candidate_developers(
        database=database,
        bug_topic_id=int(main_topic_id),
    )

    if not candidates:
        return {
            "summary": summary,
            "component": component,
            "topic_id": int(main_topic_id),
            "topic_prob": float(main_topic_prob) if main_topic_prob is not None else None,
            "recommended_developers": [],
            "reason": "no_candidate_developers_for_topic",
        }

    # 3) Siapkan pseudo bug context (mirip dengan bug existing)
    bug_ctx = {
        "topic_id": int(main_topic_id),
        "component": component,
        "summary": summary,
    }

    feature_rows: List[Dict[str, float]] = []
    meta_rows: List[Dict[str, Any]] = []

    for dev_ctx in candidates:
        feat, meta = build_feature_row(bug_ctx, dev_ctx)
        feature_rows.append(feat)
        meta_rows.append(meta)

    if not feature_rows:
        return {
            "summary": summary,
            "component": component,
            "topic_id": int(main_topic_id),
            "topic_prob": float(main_topic_prob) if main_topic_prob is not None else None,
            "recommended_developers": [],
            "reason": "no_features_built",
        }

    # 4) Susun X sesuai FEATURE_COLUMNS
    X = np.array([[row[col] for col in FEATURE_COLUMNS] for row in feature_rows])

    # 5) Load model LTR khusus org+project
    model = load_ltr_model(organization, project)
    scores = model.predict(X)

    # 6) Gabungkan skor + metadata developer
    recs: List[Dict[str, Any]] = []
    for meta, score in zip(meta_rows, scores):
        item = {
            **meta,
            "score": float(score),
        }
        recs.append(item)

    recs.sort(key=lambda x: x["score"], reverse=True)

    return {
        "summary": summary,
        "component": component,
        "topic_id": int(main_topic_id),
        "topic_prob": float(main_topic_prob) if main_topic_prob is not None else None,
        "total_candidates": len(recs),
        "recommended_developers": recs[:top_k],
    }
