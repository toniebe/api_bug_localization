from neo4j import GraphDatabase, basic_auth
uri = "bolt://localhost:7687"  # atau ambil dari env
auth = basic_auth("neo4j", "neo4j2025")

driver = GraphDatabase.driver(uri, auth=auth, encrypted=False)
with driver:
    driver.verify_connectivity()
    print("OK: connected", driver.get_server_info())
