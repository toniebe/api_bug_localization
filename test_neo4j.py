from neo4j import GraphDatabase

URI = "bolt://localhost:7687"
USER = "neo4j"
PASSWORD = "neo4j2025"
DB = "idneasyfix"  # atau 'neo4j'

driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))

with driver:
    with driver.session(database=DB) as session:
        rec = session.run("RETURN 1 AS ok").single()
        print("OK:", rec["ok"])
