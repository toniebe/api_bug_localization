# app/api/routes/feedback_route.py
from fastapi import APIRouter, Depends, Path, status, HTTPException

from app.models.feedback import BugFeedbackCreate
from app.services.feedback_service import submit_bug_feedback
from app.deps import get_current_user  

router = APIRouter(
    prefix="/{org_id}/{project_id}/feedback",
    tags=["feedback"],
)


def _uid(u):
    return u["uid"] if isinstance(u, dict) else getattr(u, "uid", None)


@router.post(
    "/bug",
    status_code=status.HTTP_201_CREATED,
)
async def give_bug_feedback(
    payload: BugFeedbackCreate,
    user = Depends(get_current_user),
):
    """
    Endpoint untuk memberi feedback apakah sebuah bug relevan
    atau tidak terhadap query & topic tertentu.
    Feedback disimpan per project dan dipakai untuk update LTM (HAS_TOPIC).
    """
    if not _uid(user):
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Sesuaikan properti user dengan model auth-mu
    user_uid = getattr(user, "uid", None) or getattr(user, "id", None)

    effect = await submit_bug_feedback(
        user_uid=user_uid,
        org_id=payload.organization,
        project_id=payload.project,
        payload=payload,
        save_to_firestore=True,
    )

    # bangun pesan deskriptif
    if effect["action"] == "increase_weight":
        msg = (
            f"Menaikkan weight HAS_TOPIC untuk topic {effect['topic_id']} "
            f"dari {effect['old_weight']} → {effect['new_weight']}."
        )
    else:
        msg = (
            f"Menurunkan weight HAS_TOPIC untuk topic {effect['topic_id']} "
            f"dari {effect['old_weight']} → {effect['new_weight']}."
        )

    if effect["old_primary_topic"] != effect["new_primary_topic"]:
        msg += (
            f" Primary topic berubah dari {effect['old_primary_topic']} "
            f"ke {effect['new_primary_topic']}."
        )
    else:
        msg += " Primary topic tidak berubah."

    return {
        "status": "success",
        "effect": effect,
        "message": msg,
    }
