from __future__ import annotations
from neo4j import GraphDatabase, basic_auth
from app.config import settings
from neo4j import AsyncGraphDatabase

_uri = settings.NEO4J_URI.strip()
_auth = basic_auth(settings.NEO4J_USER, settings.NEO4J_PASSWORD)

driver = GraphDatabase.driver(
    _uri,
    auth=_auth,
)

def get_session():
    return driver.session(database=settings.NEO4J_DATABASE)


_driver = None

async def get_driver():
    global _driver
    if _driver is None:
        _driver = AsyncGraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
            max_connection_lifetime=300,
            max_connection_pool_size=50,
        )
    return _driver

async def close_driver():
    global _driver
    if _driver is not None:
        await _driver.close()
        _driver = None
