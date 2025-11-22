from __future__ import annotations

from typing import Dict, Any, List
from app.core.neo4j_conn import get_driver


class BugRepository:
    def __init__(self):
        # Tidak menyimpan driver di sini.
        # Driver diambil per-call via await get_driver()
        pass

    async def create_bug_with_relations(
        self,
        db_name: str,
        bug: Dict[str, Any],
        similar_edges: List[Dict[str, Any]],
    ) -> None:
        """
        - MERGE :Bug
        - MERGE :Topic + [:HAS_TOPIC]
        - MERGE :Developer + [:CREATED_BY]/[:ASSIGNED_TO]
        - MERGE :Commit + [:HAS_COMMIT]
        - MERGE :DEPENDS_ON (explicit)
        - MERGE :BUG_RELATION {relation: 'similar'/'duplicate', score, source}
        """

        cypher = """
        MERGE (b:Bug { bug_id: $bug_id })
        ON CREATE SET
            b.summary          = $summary,
            b.status           = $status,
            b.resolution       = $resolution,
            b.product          = $product,
            b.component        = $component,
            b.creator          = $creator,
            b.assigned_to      = $assigned_to,
            b.creation_time    = $creation_time,
            b.last_change_time = $last_change_time,
            b.keywords         = $keywords,
            b.url              = $url,
            b.depends_on       = $depends_on,
            b.dupe_of          = $dupe_of,
            b.commit_messages  = $commit_messages,
            b.files_changed    = $files_changed,
            b.organization     = $organization,
            b.project          = $project,
            b.main_topic_id    = $main_topic_id,
            b.topic_distribution = $topic_distribution
        ON MATCH SET
            b.summary          = $summary,
            b.status           = $status,
            b.resolution       = $resolution,
            b.last_change_time = $last_change_time,
            b.main_topic_id    = $main_topic_id,
            b.topic_distribution = $topic_distribution

        WITH b,
             $main_topic_id  AS topic_id,
             $creator        AS creator_email,
             $assigned_to    AS assigned_email,
             $commit_refs    AS commit_refs,
             $depends_on     AS dep_list,
             $similar_edges  AS similar_edges

        // --- Topic ---
        FOREACH (tid IN (CASE WHEN topic_id IS NULL THEN [] ELSE [topic_id] END) |
            MERGE (t:Topic { topic_id: tid })
            MERGE (b)-[:HAS_TOPIC]->(t)
        )

        // --- Developer: creator ---
        FOREACH (devEmail IN [creator_email] |
            FOREACH (_ IN CASE WHEN devEmail IS NULL OR devEmail = '' THEN [] ELSE [1] END |
                MERGE (d:Developer { dev_id: devEmail })
                MERGE (b)-[:CREATED_BY]->(d)
            )
        )

        // --- Developer: assigned_to ---
        FOREACH (devEmail IN [assigned_email] |
            FOREACH (_ IN CASE WHEN devEmail IS NULL OR devEmail = '' THEN [] ELSE [1] END |
                MERGE (d:Developer { dev_id: devEmail })
                MERGE (b)-[:ASSIGNED_TO]->(d)
            )
        )

        // --- Commit ---
        FOREACH (ref IN commit_refs |
            MERGE (c:Commit { commit_id: ref })
            MERGE (b)-[:HAS_COMMIT]->(c)
        )

        // --- DEPENDS_ON (explicit Bugzilla field) ---
        FOREACH (dep IN dep_list |
            MERGE (depBug:Bug { bug_id: toString(dep) })
            MERGE (b)-[:DEPENDS_ON]->(depBug)
        )

        // --- SIMILAR / DUPLICATE (LDA + dupe_of) ---
        FOREACH (edge IN similar_edges |
            MERGE (other:Bug { bug_id: edge.target_bug_id })
            MERGE (b)-[r:BUG_RELATION]->(other)
            SET r.relation = edge.relation,
                r.score    = edge.score,
                r.source   = edge.source
        )
        """

        defaults = {
            "resolution": None,
            "keywords": [],
            "url": "",
            "depends_on": [],
            "dupe_of": None,
            "commit_messages": [],
            "files_changed": [],
            "commit_refs": [],
            "main_topic_id": None,
            # penting: sekarang STRING, bukan list/dict
            "topic_distribution": "",
        }
        params = {**defaults, **bug}
        params["similar_edges"] = similar_edges

        driver = await get_driver()
        async with driver.session(database=db_name) as session:
            await session.run(cypher, **params)
