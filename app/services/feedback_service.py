# app/services/feedback_service.py
from fastapi import HTTPException
from firebase_admin import firestore
from app.core.neo4j_conn import get_driver
from app.models.feedback import BugFeedbackCreate
from app.helper import _dbname, normalize_topic_id


async def submit_bug_feedback(
    user_uid: str,
    org_id: str,
    project_id: str,
    payload: BugFeedbackCreate,
    save_to_firestore: bool = True,
) -> dict:

    # Save feedback log
    if save_to_firestore:
        db = firestore.client()
        (
            db.collection("organizations")
              .document(org_id)
              .collection("projects")
              .document(project_id)
              .collection("feedback")
              .add(
                  {
                      "user_uid": user_uid,
                      "organization": payload.organization,
                      "project": payload.project,
                      "bug_id": payload.bug_id,
                      "topic_id": payload.topic_id,
                      "query": payload.query,
                      "is_relevant": payload.is_relevant,
                      "created_at": firestore.SERVER_TIMESTAMP,
                  }
              )
        )

    driver = await get_driver()
    dbname = _dbname(payload.organization, payload.project)

    bug_id = payload.bug_id
    topic_id = normalize_topic_id(payload.topic_id)

    effect = {}

    async with driver.session(database=dbname) as session:

        # =====================================================
        # 👍 RELEVANT → INCREASE WEIGHT
        # =====================================================
        if payload.is_relevant:

            result = await session.run(
                """
                MATCH (b:Bug {bug_id: $bug_id})
                WITH b, $topic_id AS tid

                // Find existing Topic if any
                OPTIONAL MATCH (t:Topic {topic_id: tid})

                // Create or reuse Topic
                WITH b, tid,
                     coalesce(t, NULL) AS tExist
                MERGE (tFinal:Topic {topic_id: tid})

                // tFinal is guaranteed Topic node
                MERGE (b)-[r:HAS_TOPIC]->(tFinal)
                WITH r, coalesce(r.weight, 0) AS old_weight
                SET r.weight = old_weight + 1
                RETURN old_weight, r.weight AS new_weight
                """,
                bug_id=bug_id,
                topic_id=topic_id,
            )

            rec = await result.single()
            old_weight = rec["old_weight"]
            new_weight = rec["new_weight"]

            # Recalculate primary topic
            result2 = await session.run(
                """
                MATCH (b:Bug {bug_id: $bug_id})
                WITH b, b.topic_id AS old_topic_id, b.topic_prob AS old_topic_prob
                OPTIONAL MATCH (b)-[r:HAS_TOPIC]->(t)
                WITH b, old_topic_id, old_topic_prob, r, t
                ORDER BY r.weight DESC
                LIMIT 1
                SET b.topic_id = CASE WHEN t IS NULL THEN old_topic_id ELSE t.topic_id END,
                    b.topic_prob = CASE WHEN r IS NULL THEN old_topic_prob ELSE r.weight END
                RETURN old_topic_id, old_topic_prob,
                       b.topic_id AS new_topic_id,
                       b.topic_prob AS new_topic_prob
                """,
                bug_id=bug_id,
            )

            rec2 = await result2.single()

            effect = {
                "action": "increase_weight",
                "topic_id": topic_id,
                "old_weight": old_weight,
                "new_weight": new_weight,
                "old_primary_topic": rec2["old_topic_id"],
                "new_primary_topic": rec2["new_topic_id"],
                "old_primary_score": rec2["old_topic_prob"],
                "new_primary_score": rec2["new_topic_prob"],
            }

        # =====================================================
        # 👎 NOT RELEVANT → DECREASE WEIGHT
        # =====================================================
        else:
            result = await session.run(
                """
                MATCH (b:Bug {bug_id: $bug_id})
                MATCH (t:Topic {topic_id: $topic_id})
                MATCH (b)-[r:HAS_TOPIC]->(t)
                WITH r, coalesce(r.weight, 0) AS old_weight
                SET r.weight = old_weight - 1
                RETURN old_weight, r.weight AS new_weight
                """,
                bug_id=bug_id,
                topic_id=topic_id,
            )

            rec = await result.single()

            # 🔴 TANGANI KALAU TIDAK ADA ROW / RELASI
            if rec is None:
                raise HTTPException(
                    status_code=404,
                    detail=(
                        f"HAS_TOPIC relation untuk bug_id={bug_id} "
                        f"dan topic_id={topic_id} tidak ditemukan"
                    ),
                )

            old_weight = rec["old_weight"]
            new_weight = rec["new_weight"]

            # remove bad relations
            await session.run(
                """
                MATCH (b:Bug {bug_id: $bug_id})
                MATCH (t:Topic {topic_id: $topic_id})
                MATCH (b)-[r:HAS_TOPIC]->(t)
                WHERE coalesce(r.weight, 0) <= -2
                DELETE r
                """,
                bug_id=bug_id,
                topic_id=topic_id,
            )

            # recalc primary
            result2 = await session.run(
                """
                MATCH (b:Bug {bug_id: $bug_id})
                WITH b, b.topic_id AS old_topic_id, b.topic_prob AS old_topic_prob
                OPTIONAL MATCH (b)-[r:HAS_TOPIC]->(t)
                WITH b, old_topic_id, old_topic_prob, r, t
                ORDER BY r.weight DESC
                LIMIT 1
                SET b.topic_id = CASE WHEN t IS NULL THEN old_topic_id ELSE t.topic_id END,
                    b.topic_prob = CASE WHEN r IS NULL THEN old_topic_prob ELSE r.weight END
                RETURN old_topic_id, old_topic_prob,
                       b.topic_id AS new_topic_id,
                       b.topic_prob AS new_topic_prob
                """,
                bug_id=bug_id,
            )

            rec2 = await result2.single()

            effect = {
                "action": "decrease_weight",
                "topic_id": topic_id,
                "old_weight": old_weight,
                "new_weight": new_weight,
                "old_primary_topic": rec2["old_topic_id"],
                "new_primary_topic": rec2["new_topic_id"],
                "old_primary_score": rec2["old_topic_prob"],
                "new_primary_score": rec2["new_topic_prob"],
            }

    return effect
