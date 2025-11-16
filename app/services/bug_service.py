# app/services/bug_service.py
from __future__ import annotations
from typing import List, Dict, Any, Optional
import re

from app.core.neo4j_conn import get_driver


def _dbname(org: str, proj: str) -> str:
    """
    Generate Neo4j database name from organization + project.
    MUST be konsisten dengan database_name di Firestore (project_service).
    Example: "EasyFix Labs" + "Alpha Project" -> "easyfix_labs_alpha_project"
    """
    def to_db(x: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", x.strip().lower()).strip("_")
    base = f"{to_db(org)}{to_db(proj)}"
    return base[:63] if len(base) > 63 else base


# ===== Bugs =====
async def list_bugs(
    organization_name: str,
    project_name: str,
    limit: int = 50,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    dbname = _dbname(organization_name, project_name)
    driver = await get_driver()

    query = """
    MATCH (b:Bug)
    RETURN b.bug_id AS bug_id,
           b.status AS status,
           b.assigned_to as asignee,
           b.clean_text as description,
           b.summary as summary
    ORDER BY b.bug_id
    SKIP $offset LIMIT $limit
    """

    async with driver.session(database=dbname) as session:
        result = await session.run(query, {"offset": offset, "limit": limit})
        records = [dict(record) async for record in result]

    return records


async def get_bug_detail(
    organization_name: str,
    project_name: str,
    bug_id: str,
) -> Optional[Dict[str, Any]]:
    dbname = _dbname(organization_name, project_name)
    driver = await get_driver()

    query = """
    MATCH (b:Bug {bug_id: $bug_id})
    OPTIONAL MATCH (b)-[:ASSIGNED_TO]->(d:Developer)
    OPTIONAL MATCH (b)-[:IN_PROJECT]->(p:Project)
    OPTIONAL MATCH (b)-[:HAS_TOPIC]->(t:Topic)
    RETURN b AS bug,
           collect(DISTINCT d) AS devs,
           collect(DISTINCT p) AS projects,
           collect(DISTINCT t) AS topics
    """

    async with driver.session(database=dbname) as session:
        result = await session.run(query, {"bug_id": bug_id})
        record = await result.single()

    if not record:
        return None

    bug_node = record["bug"]
    bug = bug_node._properties if bug_node is not None else {}

    devs     = [n._properties for n in record["devs"]     if n is not None]
    projects = [n._properties for n in record["projects"] if n is not None]
    topics   = [n._properties for n in record["topics"]   if n is not None]

    return {
        "bug": bug,
        "developers": devs,
        "projects": projects,
        "topics": topics,
    }


# ===== Developers =====
async def list_developers(
    organization_name: str,
    project_name: str,
    limit: int = 50,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    dbname = _dbname(organization_name, project_name)
    driver = await get_driver()

    query = """
    MATCH (d:Developer)
    RETURN d.dev_id AS email
    ORDER BY COALESCE(d.dev_id, d.email)
    SKIP $offset LIMIT $limit
    """

    async with driver.session(database=dbname) as session:
        result = await session.run(query, {"offset": offset, "limit": limit})
        records = [dict(record) async for record in result]

    return records


async def get_developer_detail(
    organization_name: str,
    project_name: str,
    dev_key: str,   # bisa dev_id atau email
) -> Optional[Dict[str, Any]]:
    dbname = _dbname(organization_name, project_name)
    driver = await get_driver()

    query = """
    MATCH (d:Developer)
    WHERE d.dev_id = $k OR d.email = $k
    OPTIONAL MATCH (d)<-[:ASSIGNED_TO]-(b:Bug)
    OPTIONAL MATCH (d)-[:CONTRIBUTES_TO]->(p:Project)
    RETURN d AS dev,
           collect(DISTINCT b) AS bugs,
           collect(DISTINCT p) AS projects
    """

    async with driver.session(database=dbname) as session:
        result = await session.run(query, {"k": dev_key})
        record = await result.single()

    if not record:
        return None

    dev_node = record["dev"]
    dev = dev_node._properties if dev_node is not None else {}
    bugs     = [n._properties for n in record["bugs"]     if n is not None]
    projects = [n._properties for n in record["projects"] if n is not None]

    return {
        "developer": dev,
        "bugs": bugs,
        "projects": projects,
    }


# ===== Topics =====
async def list_topics(
    organization_name: str,
    project_name: str,
    limit: int = 100,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    dbname = _dbname(organization_name, project_name)
    driver = await get_driver()

    query = """
    MATCH (t:Topic)
    RETURN t.topic_id AS topic_id,
           t.terms     AS terms,
           t.topic_label   AS topic_label
    ORDER BY t.topic_id
    SKIP $offset LIMIT $limit
    """

    async with driver.session(database=dbname) as session:
        result = await session.run(query, {"offset": offset, "limit": limit})
        records = [dict(record) async for record in result]

    return records
