import time
from typing import List, Tuple
from app.core.neo4j_conn import get_session
from app.services.nlp_service import tokenize
from app.core.firebase import db
from firebase_admin import firestore

# --- Cypher util ---
# Skema asumsi:
# (:Bug {id,title,description,status})
# (:Commit {id,sha,message})
# (:Developer {id,name,email})
# Rel:
# (Bug)-[:FIXED_BY]->(Commit)
# (Commit)-[:AUTHORED_BY]->(Developer)
# (Bug)-[:ASSIGNED_TO]->(Developer)

CYPHER_SEARCH = """
MATCH (b:Bug)
OPTIONAL MATCH (b)-[:ASSIGNED_TO]->(devAss:Developer)
WITH b, devAss
WHERE (
  size($tokens) = 0 OR
  ANY(t IN $tokens WHERE
      toLower(coalesce(b.title,''))     CONTAINS t OR
      toLower(coalesce(b.description,'')) CONTAINS t)
)
OPTIONAL MATCH (b)-[:FIXED_BY]->(c:Commit)
OPTIONAL MATCH (c)-[:AUTHORED_BY]->(devCom:Developer)
WITH b, devAss, c, devCom
RETURN b{ .id, .title, .description, .status } AS bug,
       devAss{ .id, .name, .email }           AS assigned_to,
       collect(DISTINCT c{ .id, .message, .sha }) AS commits_raw,
       collect(DISTINCT devCom{ .id, .name, .email }) AS commit_devs
LIMIT $limit
"""

def search_graph(raw_query: str, user_uid: str, limit: int = 50):
    t0 = time.time()
    tokens = tokenize(raw_query)
    tokens_lower = [t.lower() for t in tokens]

    bugs: List[dict] = []
    dev_set, commit_set = set(), set()

    with get_session() as session:
        records = session.run(CYPHER_SEARCH, tokens=tokens_lower, limit=limit)
        for r in records:
            bug = r["bug"] or {}
            assigned = r["assigned_to"] or {}
            commits_raw = r["commits_raw"] or []
            commit_devs = r["commit_devs"] or []

            commits_out = []
            for c in commits_raw:
                if not c: 
                    continue
                cid = str(c.get("id"))
                if cid in commit_set:
                    continue
                commit_set.add(cid)
                # coba cari author dari list dev commit_devs (first match ok untuk demo)
                author = None
                if commit_devs:
                    d = commit_devs[0]
                    if d:
                        author = {
                            "id": str(d.get("id")),
                            "name": d.get("name"),
                            "email": d.get("email"),
                        }
                        dev_set.add(str(d.get("id")))
                commits_out.append({
                    "id": cid,
                    "message": c.get("message"),
                    "sha": c.get("sha"),
                    "author": author
                })

            if assigned:
                dev_set.add(str(assigned.get("id")))

            bugs.append({
                "id": str(bug.get("id")),
                "title": bug.get("title"),
                "description": bug.get("description"),
                "status": bug.get("status"),
                "assigned_to": {
                    "id": str(assigned.get("id")) if assigned else None,
                    "name": assigned.get("name") if assigned else None,
                    "email": assigned.get("email") if assigned else None,
                } if assigned else None,
                "commits": commits_out
            })

    took_ms = int((time.time() - t0) * 1000)

    # --- Logging transaksi ke Firestore ---
    db.collection("search_logs").add({
        "user_uid": user_uid,
        "query": raw_query,
        "tokens": tokens_lower,
        "result_counts": {
            "bugs": len(bugs),
            "commits": len(commit_set),
            "developers": len(dev_set),
        },
        "took_ms": took_ms,
        "created_at": firestore.SERVER_TIMESTAMP,
    })

    return {
        "query": raw_query,
        "tokens": tokens_lower,
        "total_bugs": len(bugs),
        "total_commits": len(commit_set),
        "total_developers": len(dev_set),
        "bugs": bugs
    }
