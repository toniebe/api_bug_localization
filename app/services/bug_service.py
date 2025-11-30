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

DEFAULT_SIM_THRESHOLD = 0.60
DEFAULT_DUP_THRESHOLD = 0.80


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
        """
        Proses add new bug:
        - NLTK preprocess + LDA (LTM) per db_name
        - Cari similar / duplicate bugs (LDA-based)
        - Tambah relasi depends_on & duplicate dari field Bugzilla
        - Simpan ke Neo4j via BugRepository
        """
        bug_id = str(bug.id)

        # 1) NLTK + LDA (LTM)
        text_for_topic = bug.summary  # bisa ditambah description kalau nanti ada
        topic_info = self.nlp.infer_topics(db_name=db_name, text=text_for_topic)
        main_topic_id = topic_info["main_topic_id"]
        topic_distribution = topic_info["topic_distribution"]

        # serialize distribusi topic → list[dict] → JSON string
        topic_distribution_serialized = [
            {"topic_id": int(tid), "prob": float(prob)}
            for tid, prob in topic_distribution
        ]
        topic_distribution_json = json.dumps(topic_distribution_serialized)

        # 2) Similar / duplicate (LDA-based)
        similar_edges: List[Dict[str, Any]] = []
        if topic_distribution:
            similar_edges = self.nlp.find_similar_bugs(
                db_name=db_name,
                topic_distribution=topic_distribution,
                sim_threshold=self.sim_threshold,
                dup_threshold=self.dup_threshold,
                top_k=20,
            )

        # 3) explicit duplicate dari field 'dupe_of'
        if bug.dupe_of is not None:
            similar_edges.append(
                {
                    "target_bug_id": str(bug.dupe_of),
                    "score": 1.0,
                    "relation": "duplicate",
                    "source": "bugzilla_field",
                }
            )

        # 4) Build payload ke Neo4j
        bug_doc: Dict[str, Any] = {
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
            "main_topic_id": main_topic_id,
            "topic_distribution": topic_distribution_json,
        }

        # buang None supaya tidak kirim key kosong ke Neo4j
        bug_doc = {k: v for k, v in bug_doc.items() if v is not None}

        # 5) Simpan ke Neo4j (+ relasi)
        await self.repo.create_bug_with_relations(
            db_name=db_name,
            bug=bug_doc,
            similar_edges=similar_edges,
        )

        # 6) Response singkat ke client
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