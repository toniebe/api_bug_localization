# app/services/search_service.py
from typing import List, Tuple, Dict, Set
from app.models.search import Bug, Developer, Commit, RelationEdge
from app.core.neo4j_conn import get_driver
from app.services.nlp_query import preprocess_query
import re


def _dbname(org: str, proj: str) -> str:
    def to_db(x: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", x.strip().lower()).strip("_")
    base = f"{to_db(org)}{to_db(proj)}"
    return base[:63] if len(base) > 63 else base


async def search_relevant_bugs(
    organization: str,
    project: str,
    query: str,
    limit: int = 20,
) -> Tuple[List[Bug], List[Developer], List[Commit], List[RelationEdge]]:
    dbname = _dbname(organization, project)
    driver = await get_driver()

    # --- NLTK preprocessing ---
    q_proc = preprocess_query(query)
    terms = q_proc["stems"]

    cypher = """
    MATCH (b:Bug)
    WITH b, $terms AS terms
    WHERE any(t IN terms WHERE
        toLower(coalesce(b.summary, ''))    CONTAINS t OR
        toLower(coalesce(b.clean_text, '')) CONTAINS t
    )
    WITH b,
         size([t IN terms WHERE
            toLower(coalesce(b.summary, ''))    CONTAINS t OR
            toLower(coalesce(b.clean_text, '')) CONTAINS t
         ]) AS score
    ORDER BY score DESC, b.creation_time DESC
    LIMIT $limit
    RETURN b AS bug, score
    """

    bugs: List[Bug] = []
    dev_index: Dict[str, Developer] = {}
    dev_bugs: Dict[str, Set[str]] = {}

    commit_index: Dict[str, Commit] = {}
    commit_bugs: Dict[str, Set[str]] = {}

    # kita pakai set untuk dedup edge
    edge_set: Set[tuple] = set()

    async with driver.session(database=dbname) as session:
        result = await session.run(cypher, {"terms": terms, "limit": limit})

        async for r in result:
            bug_node = r["bug"]
            score = r["score"]

            bug_id = str(bug_node["bug_id"])

            # ---------- BUG ----------
            bugs.append(
                Bug(
                    bug_id=bug_id,
                    title=bug_node.get("summary"),
                    description=bug_node.get("clean_text"),
                    status=bug_node.get("status"),
                    created_at=bug_node.get("creation_time"),
                    score=score,
                )
            )

            # ---------- DEVELOPER ----------
            assigned = bug_node.get("assigned_to")
            if assigned:
                dev_id = assigned   # gunakan email sebagai ID
                if dev_id not in dev_index:
                    dev_index[dev_id] = Developer(
                        developer_id=dev_id,
                        name=dev_id,
                        email=dev_id,
                        total_fixed_bugs=None,
                        bug_ids=[],
                    )
                    dev_bugs[dev_id] = set()

                dev_bugs[dev_id].add(bug_id)

                edge_set.add((
                    "bug", bug_id,
                    "developer", dev_id,
                    "ASSIGNED_TO",
                ))

            # ---------- COMMITS ----------
            messages_raw = bug_node.get("commit_messages") or ""
            refs_raw = bug_node.get("commit_refs") or ""

            messages = [m.strip() for m in messages_raw.split(";") if m.strip()]
            refs = [u.strip() for u in refs_raw.split(";") if u.strip()]

            for idx, msg in enumerate(messages):
                commit_id = f"{bug_id}_{idx}"

                if commit_id not in commit_index:
                    url = refs[idx] if idx < len(refs) else None

                    commit_index[commit_id] = Commit(
                        commit_id=commit_id,
                        hash=commit_id,
                        message=msg,
                        repository=url,
                        committed_at=None,
                        bug_ids=[],
                    )
                    commit_bugs[commit_id] = set()

                commit_bugs[commit_id].add(bug_id)

                edge_set.add((
                    "bug", bug_id,
                    "commit", commit_id,
                    "FIXED_IN",
                ))

    # inject bug_ids ke Developer & Commit
    for dev_id, b_ids in dev_bugs.items():
        dev_index[dev_id].bug_ids = sorted(b_ids)

    for commit_id, b_ids in commit_bugs.items():
        commit_index[commit_id].bug_ids = sorted(b_ids)

    # convert edge_set -> list[RelationEdge]
    edges: List[RelationEdge] = [
        RelationEdge(
            source_type=s_t,
            source_id=s_id,
            target_type=t_t,
            target_id=t_id,
            relation_type=rel,
        )
        for (s_t, s_id, t_t, t_id, rel) in edge_set
    ]

    developers = list(dev_index.values())
    commits = list(commit_index.values())

    return bugs, developers, commits, edges
