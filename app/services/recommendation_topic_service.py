from typing import List, Dict, Any
from app.core.neo4j_conn import get_driver
from app.helper import _dbname


async def recommend_developers_for_topic(
    organization_name: str,
    project_name: str,
    topic_id: int,
    limit: int = 10,
) -> Dict[str, Any]:
    driver = await get_driver()

    cypher = """
    MATCH (t:Topic {topic_id: $topic_id})
    WITH t

    // DEV yang pernah handle bug FIXED dengan topik ini
    MATCH (bTopic:Bug)-[:HAS_TOPIC]->(t)
    MATCH (bTopic)-[:ASSIGNED_TO]->(d:Developer)
    WHERE bTopic.status = "RESOLVED"
    AND bTopic.resolution = "FIXED"
    WITH t, d, count(bTopic) AS bugs_fixed_topic

    // TOTAL bug FIXED yg pernah dia handle (semua topic)
    MATCH (bAll:Bug)-[:ASSIGNED_TO]->(d)
    WHERE bAll.status = "RESOLVED"
    AND bAll.resolution = "FIXED"
    WITH t,
        d,
        bugs_fixed_topic,
        count(bAll) AS bugs_fixed_total,
        1.0 * bugs_fixed_topic / count(bAll) AS topic_score

    RETURN
    t.topic_id AS topic_id,
    t.topic_label AS topic_name,
    d.dev_id AS developer_id,
    bugs_fixed_topic,
    bugs_fixed_total,
    topic_score
    ORDER BY topic_score DESC, bugs_fixed_topic DESC
    LIMIT $limit

    """

    database = _dbname(organization_name, project_name)
    async with driver.session(database=database) as session:
        result = await session.run(cypher, topic_id=topic_id, limit=limit)
        rows = [record async for record in result]

    developers = []
    topic_name = None
    for r in rows:
        topic_name = r["topic_name"]
        developers.append({
            "developer_id": r["developer_id"],
            "bugs_fixed_topic": r["bugs_fixed_topic"],
            "bugs_fixed_total": r["bugs_fixed_total"],
            "topic_score": float(r["topic_score"]),
        })

    return {
        "topic_id": topic_id,
        "topic_name": topic_name,
        "total_recommended": len(developers),
        "developers": developers,
    }
