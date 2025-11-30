from typing import List, Dict, Any, Optional
from app.core.neo4j_conn import get_driver
from app.services.bug_service import _dbname

async def recommend_developers_for_bug(
    organization_name: str,
    project_name: str,
    bug_id: str,
    limit: int = 5,
) -> List[Dict[str, Any]]:
    driver = await get_driver()

    cypher = """
        MATCH (targetBug:Bug {bug_id: $bug_id})
        WHERE targetBug.topic_id IS NOT NULL

        // dev yang pernah handle bug dengan topic yang sama
        MATCH (d:Developer)<-[:ASSIGNED_TO]-(bSame:Bug)
        WHERE bSame.topic_id = targetBug.topic_id

        WITH targetBug, d,
            collect(bSame.bug_id) AS related_bug_ids,
            count(bSame) AS same_topic_bugs

        // semua bug yang pernah dia handle (semua topic)
        MATCH (d)<-[:ASSIGNED_TO]-(bAll:Bug)
        WITH targetBug, d, related_bug_ids, same_topic_bugs, count(bAll) AS total_bugs

        WITH d,
            related_bug_ids[0..5] AS sample_related_bug_ids,
            same_topic_bugs,
            total_bugs,
            1.0 * same_topic_bugs / total_bugs AS topic_score

        RETURN
        d.dev_id AS developer_id,
        d.name AS name,
        same_topic_bugs,
        total_bugs,
        topic_score,
        sample_related_bug_ids
        ORDER BY topic_score DESC, same_topic_bugs DESC

    LIMIT $limit
    """

    dbname = _dbname(organization_name, project_name)
    async with driver.session(database=dbname) as session:
        result = await session.run(cypher, bug_id=bug_id, limit=limit)
        records = [record async for record in result]

    recommendations: List[Dict[str, Any]] = []

    for r in records:
        recommendations.append({
            "developer_id": r["developer_id"],
            "name": r["name"],
            "same_topic_bugs": r["same_topic_bugs"],
            "total_bugs": r["total_bugs"],
            "topic_score": float(r["topic_score"]),
            "sample_related_bug_ids": r["sample_related_bug_ids"],
        })

    return recommendations
