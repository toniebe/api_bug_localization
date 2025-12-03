# app/services/bug_service.py
from __future__ import annotations

from typing import List, Dict, Any, Optional
import os
import re
import json

from app.core.neo4j_conn import get_driver
from app.models.bug import BugIn, BugOut
from app.repositories.bug_repository import BugRepository
from app.services.nlp_topic_service import get_nlp_topic_service
from app.helper import _dbname

DEFAULT_SIM_THRESHOLD = 0.60
DEFAULT_DUP_THRESHOLD = 0.80


# ====== LISTING / DETAIL (langsung ke Neo4j via async driver) ======

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
    WHERE d.dev_id = $k
    OPTIONAL MATCH (d)<-[:ASSIGNED_TO]-(b:Bug)
    RETURN d AS dev,
           collect(DISTINCT b) AS bugs
    """

    async with driver.session(database=dbname) as session:
        result = await session.run(query, {"k": dev_key})
        record = await result.single()

    if not record:
        return None

    dev_node = record["dev"]
    dev = dev_node._properties if dev_node is not None else {}
    bugs     = [n._properties for n in record["bugs"]     if n is not None]

    return {
        "developer": dev,
        "bugs": bugs
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


# ====== CLASS BUG SERVICE (untuk addNewBug) ======

def get_bug_service() -> "BugService":
    return BugService()


class BugService:
    def __init__(self):
        self.repo = BugRepository()
        self.nlp = get_nlp_topic_service()
        self.sim_threshold = float(os.getenv("SIM_THRESHOLD", DEFAULT_SIM_THRESHOLD))
        self.dup_threshold = float(os.getenv("DUP_THRESHOLD", DEFAULT_DUP_THRESHOLD))

    async def AddNewBug(
        self,
        db_name: str,
        organization: str,
        project: str,
        bug: BugIn,
    ) -> BugOut:

        bug_id = str(bug.id)

        # (1) Infer LDA
        text_for_topic = bug.summary
        topic_info = self.nlp.infer_topics(db_name=db_name, text=text_for_topic)
        main_topic_id = topic_info["main_topic_id"]
        topic_distribution = topic_info["topic_distribution"]

        # serialize for saving
        topic_distribution_serialized = [
            {"topic_id": int(tid), "prob": float(prob)}
            for tid, prob in topic_distribution
        ]
        topic_distribution_json = json.dumps(topic_distribution_serialized)

        # MULTI TOPIC EDGES (NEW)
        topic_edges = [
            {"topic_id": str(tid), "weight": float(prob)}
            for tid, prob in topic_distribution
        ]

        # (2) Similar edges
        similar_edges = []
        if topic_distribution:
            similar_edges = self.nlp.find_similar_bugs(
                db_name=db_name,
                topic_distribution=topic_distribution,
                sim_threshold=self.sim_threshold,
                dup_threshold=self.dup_threshold,
                top_k=20,
            )

        # (3) explicit duplicate
        if bug.dupe_of is not None:
            similar_edges.append(
                {
                    "target_bug_id": str(bug.dupe_of),
                    "score": 1.0,
                    "relation": "duplicate",
                    "source": "bugzilla_field",
                }
            )

        # (4) Build bug doc
        bug_doc = {
            "bug_id": bug_id,
            "summary": bug.summary,
            "status": bug.status,
            "resolution": bug.resolution,
            "product": bug.product,
            "component": bug.component,
            "creator": bug.creator,
            "assigned_to": bug.assigned_to,
            "creation_time": bug.creation_time,
            "last_change_time": bug.last_change_time,
            "keywords": bug.keywords,
            "url": bug.url,
            "depends_on": bug.depends_on,
            "dupe_of": bug.dupe_of,
            "commit_messages": bug.commit_messages,
            "commit_refs": bug.commit_refs,
            "files_changed": bug.files_changed,
            "organization": organization,
            "project": project,
            "main_topic_id": str(main_topic_id),   # STRING
            "topic_distribution": topic_distribution_json,
        }

        bug_doc = {k: v for k, v in bug_doc.items() if v is not None}

        # (5) Save to Neo4j
        await self.repo.create_bug_with_relations(
            db_name=db_name,
            bug=bug_doc,
            similar_edges=similar_edges,
            topic_edges=topic_edges,   # NEW
        )

        # (6) Response
        return BugOut(
            bug_id=bug_id,
            summary=bug.summary,
            status=bug.status,
            resolution=bug.resolution,
            product=bug.product,
            component=bug.component,
            creator=bug.creator,
            assigned_to=bug.assigned_to,
            creation_time=bug.creation_time,
            last_change_time=bug.last_change_time,
            keywords=bug.keywords,
            url=bug.url,
        )



async def fetch_bug_dev_pairs(database: str):
    """
    Mengambil:
    - pasangan (bug, developer yang fix)
    - developer lain sebagai negative sampling
    """

    driver = await get_driver()

    cypher = """
    MATCH (b:Bug)-[:ASSIGNED_TO]->(d:Developer)
    WHERE b.topic_id IS NOT NULL
    AND b.status = "RESOLVED"
    AND b.resolution = "FIXED"
    RETURN
      b.bug_id AS bug_id,
      d.dev_id AS developer_id,
      b.topic_id AS topic_id,
      b.component AS component,
      b.summary AS summary
    """

    async with driver.session(database=database) as session:
        result = await session.run(cypher)
        rows = [record async for record in result]


    # hasil format list[Record]
    return [dict(r) for r in rows]


async def fetch_all_developers(database: str):
    driver = await get_driver()
    cypher = """
    MATCH (d:Developer)
    RETURN
      d.dev_id AS developer_id,
      d.components AS components,
      d.last_active_at AS last_active_at
    """
    async with driver.session(database=database) as session:
        result = await session.run(cypher)
        rows = [record async for record in result]

    return [dict(r) for r in rows]