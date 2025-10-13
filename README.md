# 1) install deps
python -m venv env
source .venv/bin/activate
pip install -r requirements.txt

# 2) set env (or create .env)
export NEO4J_URI='neo4j+s://<your-aura-host>:7687'
export NEO4J_USER='neo4j'
export NEO4J_PASS='<your-password>'

# 3) start api
uvicorn app:app --reload --host 0.0.0.0 --port 8000
