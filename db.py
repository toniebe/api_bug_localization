# db.py
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict, Any, List

from dotenv import load_dotenv
from neo4j import AsyncGraphDatabase, AsyncSession

load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI", "").strip()
NEO4J_USER = os.getenv("NEO4J_USER", "").strip()
NEO4J_PASS = os.getenv("NEO4J_PASS", "").strip()
NEO4J_DB   = os.getenv("NEO4J_DB", "neo4j").strip()

if not (NEO4J_URI and NEO4J_USER and NEO4J_PASS):
    raise RuntimeError("Missing Neo4j creds: set NEO4J_URI, NEO4J_USER, NEO4J_PASS (and optional NEO4J_DB)")

driver = AsyncGraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))

async def ensure_fulltext():
    cypher = """
    CREATE FULLTEXT INDEX bug_fulltext IF NOT EXISTS
    FOR (b:bug) ON EACH [b.summary, b.topic_label]
    """
    async with driver.session(database=NEO4J_DB) as s:
        cur = await s.run(cypher)
        await cur.consume()
        
@asynccontextmanager
async def lifespan(app):
    # ping on startup (outside tx)
    async with driver.session(database=NEO4J_DB) as s:
        cur = await s.run("RETURN 1 AS ok")
        await cur.single()
        await ensure_fulltext()
    try:
        yield
    finally:
        await driver.close()

def _node_to_bug(n: Dict[str, Any]) -> Dict[str, Any]:
    """Return a plain dict that matches models.Bug (FastAPI will validate)."""
    return {
        "id": int(n["id"]),
        "summary": n.get("summary"),
        "assigned_to": n.get("assigned_to"),
        "status": n.get("status"),
        "resolution": n.get("resolution"),
        "topic": int(n["topic"]) if n.get("topic") is not None else None,
        "topic_label": n.get("topic_label"),
        "topic_score": float(n["topic_score"]) if n.get("topic_score") is not None else None,
    }

async def run(query: str, params: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    """Generic async runner that returns a list of record dictionaries."""
    rows: List[Dict[str, Any]] = []
    async with driver.session(database=NEO4J_DB) as s:
        cur = await s.run(query, params or {})
        async for rec in cur:
            rows.append(rec.data())
    return rows

async def single(query: str, params: Dict[str, Any] | None = None) -> Dict[str, Any] | None:
    async with driver.session(database=NEO4J_DB) as s:
        cur = await s.run(query, params or {})
        rec = await cur.single()
        return rec.data() if rec else None
