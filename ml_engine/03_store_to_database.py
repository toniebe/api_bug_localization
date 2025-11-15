#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import csv
import argparse
from pathlib import Path
from neo4j import GraphDatabase

HERE = Path(__file__).resolve().parent

def load_csv(path: Path):
    if not path.exists():
        print(f"[WARN] CSV not found: {path}")
        return []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader)

def neo4j_driver(uri, user, password):
    return GraphDatabase.driver(uri, auth=(user, password))


def store_topics(session, topics_rows):
    if not topics_rows:
        print("[TOPIC] No topics to store")
        return

    query = """
    UNWIND $rows AS row
    WITH row, toInteger(row.topic_id) AS topic_id
    MERGE (t:Topic {topic_id: topic_id})
    SET t += row
    """
    session.run(query, rows=topics_rows)
    print(f"[TOPIC] Stored {len(topics_rows)} topics")


def store_bugs(session, bugs_rows):
    if not bugs_rows:
        print("[BUG] No bug metadata to store")
        return

    query = """
    UNWIND $rows AS row
    WITH row, row.bug_id AS bug_id
    MERGE (b:Bug {bug_id: bug_id})
    SET b += row
    """
    session.run(query, rows=bugs_rows)
    print(f"[BUG] Stored/updated {len(bugs_rows)} bugs")


def store_developers(session, dev_rows):
    if not dev_rows:
        print("[DEV] No developers to store")
        return

    query = """
    UNWIND $rows AS row
    WITH row, row.dev_id AS dev_id
    MERGE (d:Developer {dev_id: dev_id})
    SET d += row
    """
    session.run(query, rows=dev_rows)
    print(f"[DEV] Stored/updated {len(dev_rows)} developers")


def store_commits(session, commit_rows):
    if not commit_rows:
        print("[COMMIT] No commits to store")
        return

    # Node commit
    query_commit = """
    UNWIND $rows AS row
    WITH row, row.commit_id AS commit_id
    MERGE (c:Commit {commit_id: commit_id})
    SET c += row
    """
    session.run(query_commit, rows=commit_rows)
    print(f"[COMMIT] Stored/updated {len(commit_rows)} commits")

    # Relasi Commit - Developer (AUTHORED_BY) jika ada dev_id
    query_rel_dev = """
    UNWIND $rows AS row
    WITH row
    WHERE row.dev_id IS NOT NULL AND row.dev_id <> ""
    MATCH (c:Commit {commit_id: row.commit_id})
    MATCH (d:Developer {dev_id: row.dev_id})
    MERGE (c)-[:AUTHORED_BY]->(d)
    """
    session.run(query_rel_dev, rows=commit_rows)

    # Relasi Bug - Commit (FIXED_BY) jika ada bug_id
    query_rel_bug = """
    UNWIND $rows AS row
    WITH row
    WHERE row.bug_id IS NOT NULL AND row.bug_id <> ""
    MATCH (b:Bug {bug_id: row.bug_id})
    MATCH (c:Commit {commit_id: row.commit_id})
    MERGE (b)-[:FIXED_BY]->(c)
    """
    session.run(query_rel_bug, rows=commit_rows)


def store_bug_topic_relations(session, bug_topics_rows):
    if not bug_topics_rows:
        print("[BUG_TOPIC] No bug-topic relations")
        return

    # Pastikan kolom weight/score ada; kalau tidak, default 1.0
    for row in bug_topics_rows:
        if "topic_weight" in row and row["topic_weight"] not in (None, ""):
            try:
                row["topic_weight"] = float(row["topic_weight"])
            except Exception:
                row["topic_weight"] = 1.0
        else:
            row["topic_weight"] = 1.0

    query = """
    UNWIND $rows AS row
    WITH row,
         row.bug_id AS bug_id,
         toInteger(row.topic_id) AS topic_id,
         row.topic_weight AS w
    MATCH (b:Bug {bug_id: bug_id})
    MATCH (t:Topic {topic_id: topic_id})
    MERGE (b)-[r:HAS_TOPIC]->(t)
    SET r.weight = w
    """
    session.run(query, rows=bug_topics_rows)
    print(f"[BUG_TOPIC] Stored {len(bug_topics_rows)} bug-topic relations")


def main():
    parser = argparse.ArgumentParser(description="Store LDA relations & metadata to Neo4j")
    parser.add_argument("--in_lda", type=str, default=os.getenv("PATH_LDA_OUT", "out_lda"))
    parser.add_argument("--neo4j-uri", type=str, default=os.getenv("NEO4J_URI", "bolt://localhost:7687"))
    parser.add_argument("--neo4j-user", type=str, default=os.getenv("NEO4J_USER", "neo4j"))
    parser.add_argument("--neo4j-pass", type=str, default=os.getenv("NEO4J_PASS", "password"))
    parser.add_argument("--neo4j-db", type=str, default=os.getenv("NEO4J_DB", None))
    parser.add_argument("--log_path", type=str, default=None)

    args = parser.parse_args()

    in_lda = Path(args.in_lda)

    # --- LOAD CSVs ---
    topics_csv        = in_lda / "topics.csv"
    bugs_topics_csv   = in_lda / "bugs_with_topics.csv"
    bugs_meta_csv     = in_lda / "bugs_meta.csv"       # sesuaikan dengan pipeline kamu
    developers_csv    = in_lda / "developers.csv"
    commits_csv       = in_lda / "commits.csv"

    topics_rows      = load_csv(topics_csv)
    bug_topics_rows  = load_csv(bugs_topics_csv)
    bugs_rows        = load_csv(bugs_meta_csv)
    dev_rows         = load_csv(developers_csv)
    commit_rows      = load_csv(commits_csv)

    # --- CONNECT NEO4J ---
    driver = neo4j_driver(args.neo4j_uri, args.neo4j_user, args.neo4j_pass)
    db_name = args.neo4j_db

    print(f"[NEO4J] Connecting to {args.neo4j_uri} db={db_name}")

    with driver:
        with driver.session(database=db_name) as session:
            # 1) simpan topics
            store_topics(session, topics_rows)

            # 2) simpan bugs + properties
            store_bugs(session, bugs_rows)

            # 3) simpan developers
            store_developers(session, dev_rows)

            # 4) simpan commits + relasi
            store_commits(session, commit_rows)

            # 5) simpan relasi Bug–Topic
            store_bug_topic_relations(session, bug_topics_rows)

    print("[NEO4J] Done")


if __name__ == "__main__":
    main()
