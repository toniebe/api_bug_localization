## DATABASE CONFIGURATION
- install neoj4i desktop
- create instance & database
- import file dari folder out_lda/bugs_with_labels, developer_topic_labels, topic_cleaned, bug_relations
- import cypher_script (ada di folder model graph/ neo4j_importer_cypher_script_2025-10-13.cypher)
- run import

Create a Neo4j Full-Text Index (run once)

Open Neo4j Browser and run:
````
// Full-text index over bug text fields
CREATE FULLTEXT INDEX bug_fulltext IF NOT EXISTS
FOR (b:bug) ON EACH [b.summary, b.topic_label];

// (Optional) full-text index for developer names/emails if you want direct dev search later
// CREATE FULLTEXT INDEX dev_fulltext IF NOT EXISTS
// FOR (d:developer) ON EACH [d.assigned_to];
````

This enables db.index.fulltext.queryNodes(...) which is fast and ranked.


#BACKEND for API
## 1) install deps
python -m venv env
source .venv/bin/activate
pip install -r requirements.txt

## 2) set env (or create .env) - sesuaikan dengan config database masing2
export NEO4J_URI='neo4j+s://<your-aura-host>:7687'
export NEO4J_USER='neo4j'
export NEO4J_PASS='<your-password>'

## 3) start api
uvicorn app:app --reload --host 0.0.0.0 --port 8000
