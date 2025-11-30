from typing import Dict, Any
from app.core.neo4j_conn import get_driver

from app.services.bug_service import _dbname

async def get_developer_topics(
    organization: str,
    project: str,
    developer_id: str,
) -> Dict[str, Any]:
    driver = await get_driver()

    database = _dbname(organization, project)
    cypher = """
    MATCH (d:Developer {dev_id: $developer_id})
    MATCH (b:Bug)-[:ASSIGNED_TO]->(d)
    WHERE b.topic_id IS NOT NULL
    AND b.status = "RESOLVED"
    AND b.resolution = "FIXED"
    WITH d, b.topic_id AS topic_id, count(*) AS bugs_fixed_topic

    WITH d,
        collect({topic_id: topic_id, bugs_fixed_topic: bugs_fixed_topic}) AS per_topic,
        sum(bugs_fixed_topic) AS total_bugs

    UNWIND per_topic AS t
    WITH d, total_bugs, t.topic_id AS topic_id, t.bugs_fixed_topic AS bugs_fixed_topic

    // JOIN KE NODE Topic berdasarkan topic_id
    OPTIONAL MATCH (topicNode:Topic {topic_id: toInteger(topic_id)})

    WITH d,
        total_bugs,
        topic_id,
        bugs_fixed_topic,
        coalesce(topicNode.topic_label, 'Topic ' + toString(topic_id)) AS topic_label,
        1.0 * bugs_fixed_topic / total_bugs AS topic_share

    RETURN
    d.dev_id AS developer_id,
    d.name   AS name,
    total_bugs,
    collect({
        topic_id: topic_id,
        topic_label: topic_label,
        bugs_fixed_topic: bugs_fixed_topic,
        topic_share: topic_share
    }) AS topics


    """

    async with driver.session(database=database) as session:
        result = await session.run(cypher, developer_id=developer_id)
        record = await result.single()

    if not record:
        return {}

    return {
        "developer_id": record["developer_id"],
        "total_bugs": record["total_bugs"],
        "topics": record["topics"],
    }
