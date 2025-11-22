# app/core/neo4j_conn.py
from __future__ import annotations

from neo4j import GraphDatabase, basic_auth, AsyncGraphDatabase
from app.config import settings

_uri = settings.NEO4J_URI.strip()
_auth = basic_auth(settings.NEO4J_USER, settings.NEO4J_PASSWORD)

# --- SYNC driver (kalau ada kode lama yang pakai) ---
driver = GraphDatabase.driver(
    _uri,
    auth=_auth,
    encrypted=False,
)

def get_session():
    return driver.session(database=settings.NEO4J_DATABASE)


# --- ASYNC driver (dipakai di FastAPI) ---
_async_driver = None

async def get_driver():
    
    print(f"[NEO4J] Connectivity check FAILED: {settings.NEO4J_USER} - {settings.NEO4J_PASSWORD}")
    """
    Async Neo4j driver singleton for use with `await get_driver()`.
    """
    global _async_driver
    
    print(f"[NEO4J] Connectivity check FAILED: {settings.NEO4J_USER} - {settings.NEO4J_PASSWORD}")
           
    if _async_driver is None:
        _async_driver = AsyncGraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
            max_connection_lifetime=300,
            max_connection_pool_size=50,
        )
    return _async_driver


async def close_driver():
    global _async_driver
    if _async_driver is not None:
        await _async_driver.close()
        _async_driver = None
