from neo4j import GraphDatabase, basic_auth
from app.config import settings

_uri = settings.NEO4J_URI.strip()
_auth = basic_auth(settings.NEO4J_USER, settings.NEO4J_PASSWORD)

driver = GraphDatabase.driver(
    _uri,
    auth=_auth,
    encrypted=False 
)

def get_session():
    return driver.session(database=settings.NEO4J_DATABASE)
