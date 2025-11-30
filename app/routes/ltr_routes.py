from fastapi import APIRouter, Query, HTTPException
from typing import Dict, Any
import re

from app.services.ltr_training_service import train_ltr_model
from app.services.recommendation_ltr_service import recommend_developers_ltr

router = APIRouter(
    prefix="/{organization}/{project}/ltr",
    tags=["ML Learning To Rank"],
)


def _dbname(org: str, proj: str) -> str:
    def to_db(x: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", x.strip().lower()).strip("_")
    base = f"{to_db(org)}{to_db(proj)}"
    return base[:63] if len(base) > 63 else base


@router.post("/train")
async def api_train_ltr_model(
    organization: str,
    project: str,
    force_retrain: bool = Query(False, description="Set true to overwrite existing model"),
) -> Dict[str, Any]:
    """
    Trigger training model Learning-to-Rank untuk rekomendasi developer.
    - Cek apakah model sudah ada.
    - Jika sudah ada dan force_retrain=False => skip.
    - Kalau force_retrain=True => retrain dari data terbaru.
    """

    result = await train_ltr_model(
        organization=organization,
        project=project,
        force_retrain=force_retrain,
    )

    # Kalau gagal (no data, not enough bugs, etc.)
    if result.get("status") in ("failed",):
        raise HTTPException(
            status_code=400,
            detail=result,
        )

    return result


@router.get("/recommended-developers/{bug_id}")
async def api_recommend_developers_ltr(
    organization: str,
    project: str,
    bug_id: str,
    top_k: int = Query(5, ge=1, le=50),
) -> Dict[str, Any]:
    """
    Rekomendasi developer menggunakan model Learning-to-Rank.
    """
    dbname = _dbname(organization, project)

    result = await recommend_developers_ltr(
        organization=organization,
        project=project,
        bug_id=bug_id,
        top_k=top_k,
    )

    if not result["recommended_developers"]:
        raise HTTPException(
            status_code=404,
            detail="No recommended developers found (missing topic, candidates, or features).",
        )

    return result
