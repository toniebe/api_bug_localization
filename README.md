#DATABASE CONFIGURATION
- install neoj4i desktop
- create instance & database
- import cypher_script (ada di folder model graph/ neo4j_importer_cypher_script_2025-10-13.cypher)
- run import


#BACKEND for API
# 1) install deps
python -m venv env
source .venv/bin/activate
pip install -r requirements.txt

# 2) set env (or create .env) - sesuaikan dengan config database masing2
export NEO4J_URI='neo4j+s://<your-aura-host>:7687'
export NEO4J_USER='neo4j'
export NEO4J_PASS='<your-password>'

# 3) start api
uvicorn app:app --reload --host 0.0.0.0 --port 8000
