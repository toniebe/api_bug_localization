# app/services/dashboard_service.py
from typing import Dict
import re

from app.core.neo4j_conn import get_driver
from app.helper import _dbname


async def get_basic_counts(organization: str, project: str) -> Dict[str, int]:
    dbname = _dbname(organization, project)
    driver = await get_driver()

    cypher = """
    MATCH (b:Bug)
    WITH count(b) AS bug_count
    MATCH (d:Developer)
    WITH bug_count, count(d) AS developer_count
    MATCH (c:Commit)
    RETURN bug_count, developer_count, count(c) AS commit_count
    """

    async with driver.session(database=dbname) as session:
        result = await session.run(cypher)
        record = await result.single()

    # if database is empty, record might be None
    if record is None:
        return {
            "bug_count": 0,
            "developer_count": 0,
            "commit_count": 0,
        }

    return {
        "bug_count": record["bug_count"],
        "developer_count": record["developer_count"],
        "commit_count": record["commit_count"],
    }
