# app.py
from typing import List

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from db import lifespan, run, single, _node_to_bug
from models import Bug, SimilarBug, DevRec, TopicStat, DeveloperProfile, SearchResponse

app = FastAPI(title="EasyFix API", version="1.1.0", lifespan=lifespan)

# CORS (relax for MVP)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

@app.get("/test")
async def test():
    ok = await single("RETURN 1 AS ok")
    return {"ok": bool(ok)}

@app.get("/bug/{id}", response_model=Bug)
async def get_bug(id: int):
    rec = await single("MATCH (b:bug {id:$id}) RETURN b", {"id": id})
    if not rec:
        raise HTTPException(404, f"bug {id} not found")
    return _node_to_bug(rec["b"])

@app.get("/bug/{id}/similar", response_model=List[SimilarBug])
async def similar_bugs(id: int, limit: int = Query(20, ge=1, le=200)):
    q = """
    MATCH (b:bug {id:$id})-[r:SIMILAR_TO]->(s:bug)
    RETURN s AS bug, r.similarity AS sim, r.relation AS rel
    ORDER BY sim DESC
    LIMIT $limit
    """
    rows = await run(q, {"id": id, "limit": limit})
    return [
        SimilarBug(bug=_node_to_bug(row["bug"]), similarity=float(row["sim"]), relation=row.get("rel"))
        for row in rows
    ]

@app.get("/bug/{id}/recommend-devs", response_model=List[DevRec])
async def recommend_devs(id: int, limit: int = Query(5, ge=1, le=50)):
    q = """
    MATCH (b:bug {id:$id})-[r:SIMILAR_TO]->(s:bug)
    WITH s.assigned_to AS dev, count(*) AS freq, sum(r.similarity) AS score
    WHERE dev IS NOT NULL AND dev <> ''
    RETURN dev AS developer, freq, score
    ORDER BY score DESC, freq DESC
    LIMIT $limit
    """
    rows = await run(q, {"id": id, "limit": limit})
    return [DevRec(developer=row["developer"], freq=int(row["freq"]), score=float(row["score"])) for row in rows]

@app.get("/topic/{id}/bugs", response_model=List[Bug])
async def bugs_in_topic(id: int, limit: int = Query(50, ge=1, le=500)):
    q = """
    MATCH (t:topic {id:$id})<-[:IN_TOPIC]-(b:bug)
    RETURN b
    ORDER BY b.topic_score DESC
    LIMIT $limit
    """
    rows = await run(q, {"id": id, "limit": limit})
    return [_node_to_bug(row["b"]) for row in rows]

@app.get("/topic/stats", response_model=List[TopicStat])
async def topic_stats():
    q = """
    MATCH (b:bug)-[:IN_TOPIC]->(t:topic)
    RETURN t.topic_label AS topic, count(*) AS n
    ORDER BY n DESC
    """
    rows = await run(q)
    return [TopicStat(topic=row["topic"] or "Unknown", count=int(row["n"])) for row in rows]

@app.get("/dev/{email}/profile", response_model=DeveloperProfile)
async def developer_profile(email: str, recent: int = Query(20, ge=1, le=100)):
    q = """
    MATCH (d:developer {assigned_to:$email})
    OPTIONAL MATCH (b:bug {assigned_to:$email})
    RETURN d, collect(b)[0..$recent] AS recent
    """
    rec = await single(q, {"email": email, "recent": recent})
    if not rec:
        return DeveloperProfile(assigned_to=email, dominant_topic=None, recent_bugs=[])
    d = rec["d"] or {}
    recent_nodes = rec["recent"] or []
    return DeveloperProfile(
        assigned_to=d.get("assigned_to", email),
        dominant_topic=int(d["dominant_topic"]) if d.get("dominant_topic") is not None else None,
        recent_bugs=[_node_to_bug(n) for n in recent_nodes],
    )

# Optional write endpoint (keep if you want)
@app.post("/bug/{id}/mark-duplicate/{dup_id}")
async def mark_duplicate(id: int, dup_id: int):
    q = """
    MATCH (a:bug {id:$a}), (b:bug {id:$b})
    MERGE (a)-[r:DUPLICATE_OF]->(b)
    ON CREATE SET r.createdAt = timestamp()
    RETURN a.id AS a_id, b.id AS b_id
    """
    rec = await single(q, {"a": id, "b": dup_id})
    if not rec:
        raise HTTPException(400, "unable to create DUPLICATE_OF")
    return {"ok": True, "a": rec["a_id"], "b": rec["b_id"]}

@app.get("/search", response_model=SearchResponse)
async def search(
    q: str = Query(..., min_length=2, description="User query text"),
    limit: int = Query(25, ge=1, le=200),
    dev_limit: int = Query(10, ge=1, le=100),
):
    """
    Full-text search over bug summary/topic_label, with developer ranking:
      1) Prefer assignees of SIMILAR_TO neighbors of matched bugs
      2) Fallback to assignees of matched bugs (excluding 'nobody@mozilla.org')
      3) Fallback to owners in the most-hit topics
    """

    # 0) FT search (requires: CREATE FULLTEXT INDEX bug_fulltext IF NOT EXISTS FOR (b:bug) ON EACH [b.summary, b.topic_label])
    q_ft = """
    CALL db.index.fulltext.queryNodes('bug_fulltext', $q)
    YIELD node AS b, score
    RETURN b, score
    ORDER BY score DESC
    LIMIT $limit
    """
    rows = await run(q_ft, {"q": q, "limit": limit})

    # Build bug list + (id, score) pairs for weighting
    bugs: list[Bug] = []
    pairs: list[dict] = []   # [{id:int, score:float}]
    for row in rows:
        b = row["b"]
        bugs.append(_node_to_bug(b))
        pairs.append({"id": int(b["id"]), "score": float(row["score"])})

    devs: list[DevRec] = []

    if pairs:
        # 1) Prefer assignees from similar bugs (better coverage for untriaged matches)
        q_devs_sim = """
        UNWIND $pairs AS row
        WITH toInteger(row.id) AS id, toFloat(row.score) AS s
        MATCH (:bug {id:id})-[:SIMILAR_TO]->(sbug:bug)
        WITH sbug.assigned_to AS dev, s
        WHERE dev IS NOT NULL AND dev <> '' AND dev <> 'nobody@mozilla.org'
        RETURN dev AS developer,
               count(*) AS freq,
               sum(s)   AS score
        ORDER BY score DESC, freq DESC
        LIMIT $dev_limit
        """
        sim_rows = await run(q_devs_sim, {"pairs": pairs, "dev_limit": dev_limit})
        devs = [DevRec(developer=r["developer"], freq=int(r["freq"]), score=float(r["score"])) for r in sim_rows]

        # 2) Fallback: direct assignees of matched bugs (excluding 'nobody')
        if not devs:
            q_devs_direct = """
            UNWIND $pairs AS row
            WITH toInteger(row.id) AS id, toFloat(row.score) AS s
            MATCH (b:bug {id:id})
            WITH b.assigned_to AS dev, s
            WHERE dev IS NOT NULL AND dev <> '' AND dev <> 'nobody@mozilla.org'
            RETURN dev AS developer,
                   count(*) AS freq,
                   sum(s)   AS score
            ORDER BY score DESC, freq DESC
            LIMIT $dev_limit
            """
            dir_rows = await run(q_devs_direct, {"pairs": pairs, "dev_limit": dev_limit})
            devs = [DevRec(developer=r["developer"], freq=int(r["freq"]), score=float(r["score"])) for r in dir_rows]

        # 3) Fallback: owners from most-hit topics
        if not devs:
            q_topic_owners = """
            UNWIND $pairs AS row
            WITH toInteger(row.id) AS id
            MATCH (b:bug {id:id})-[:IN_TOPIC]->(t:topic)
            WITH t.id AS topic_id, count(*) AS hits
            ORDER BY hits DESC
            LIMIT 5
            MATCH (bb:bug)-[:IN_TOPIC]->(:topic {id:topic_id})
            WITH bb.assigned_to AS dev
            WHERE dev IS NOT NULL AND dev <> '' AND dev <> 'nobody@mozilla.org'
            RETURN dev AS developer, count(*) AS freq
            ORDER BY freq DESC
            LIMIT $dev_limit
            """
            top_rows = await run(q_topic_owners, {"pairs": pairs, "dev_limit": dev_limit})
            devs = [DevRec(developer=r["developer"], freq=int(r["freq"]), score=float(r["freq"])) for r in top_rows]

    return SearchResponse(query=q, bugs=bugs, developers=devs)

