#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import csv
import argparse
import importlib.util
from pathlib import Path
from neo4j import GraphDatabase

HERE = Path(__file__).resolve().parent


# ============================================================
# CSV LOADER (ROBUST)
# ============================================================

def load_csv(path: Path):
    """
    Load CSV menjadi list[dict], aman untuk:
    - file tidak ada -> []
    - BOM (utf-8-sig)
    - extra column (disimpan DictReader di key None -> kita buang & warning)
    """
    if not path.exists():
        print(f"[WARN] CSV not found: {path}")
        return []

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = []
        for i, row in enumerate(reader, start=1):
            # kalau ada kolom ekstra, DictReader simpan di key None
            if None in row:
                extra = row.pop(None)
                print(f"[WARN] {path.name}: line {i} has extra columns -> {extra}")
            rows.append(row)

    print(f"[DEBUG] load_csv: {path} -> {len(rows)} rows")
    return rows


# ---------- helper ambil log dari main.py ----------
def get_main_module():
    here = os.path.dirname(os.path.abspath(__file__))
    main_path = os.path.join(here, "main.py")
    if not os.path.exists(main_path):
        return None
    spec = importlib.util.spec_from_file_location("main_module", main_path)
    main_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(main_mod)
    return main_mod


def neo4j_connect(uri: str, user: str, password: str, db_name: str | None = None):
    try:
        from neo4j import GraphDatabase as _GD
    except ImportError as e:
        raise RuntimeError(f"neo4j driver not installed: {e}")

    driver = _GD.driver(uri, auth=(user, password))
    try:
        if db_name:
            with driver.session(database=db_name) as session:
                session.run("RETURN 1 AS ok")
        else:
            with driver.session() as session:
                session.run("RETURN 1 AS ok")
    except Exception as e:
        raise RuntimeError(f"cannot connect to neo4j at {uri} as {user}: {e}")
    return driver


def neo4j_driver(uri, user, password):
    return GraphDatabase.driver(uri, auth=(user, password))


# ============================================================
#  TOPIC: topics_cleaned.csv + bugs_with_labels.csv
# ============================================================

def neo4j_has_bug_bug(session):
    """
    Cek apakah sudah ada relasi bug-bug di DB.
    """
    result = session.run("""
        MATCH (b1:Bug)-[r:SIMILAR_TO|DUPLICATE_OF|DEPENDS_ON]->(b2:Bug)
        RETURN count(r) AS c
    """)
    rec = result.single()
    return rec and rec["c"] > 0


def _import_topics_and_bugs(session, in_lda: Path, log_write, log_fh):
    """
    1) Import Topic dari topics_cleaned.csv
    2) Import Bug dari bugs_with_labels.csv (full properties)
    3) Import relasi Bug–Topic (HAS_TOPIC) dari bugs_with_labels.csv
    """
    topics_path = in_lda / "topics_cleaned.csv"
    bugs_path   = in_lda / "bugs_with_labels.csv"

    topics_rows = load_csv(topics_path)
    bugs_rows   = load_csv(bugs_path)

    # --- Topics ---
    if topics_rows:
        for r in topics_rows:
            try:
                r["topic_id"] = int(r["topic_id"])
            except Exception:
                pass

        session.run("""
            UNWIND $rows AS row
            MERGE (t:Topic {topic_id: row.topic_id})
            SET t += row
        """, rows=topics_rows)
        log_write(log_fh, f"[NEO4J][TOPIC] Stored/updated {len(topics_rows)} topics from topics_cleaned.csv")
    else:
        log_write(
            log_fh,
            f"[NEO4J][TOPIC] topics_cleaned.csv (path={topics_path}) not found or empty — skip Topic nodes."
        )

    # --- Bugs ---
    if bugs_rows:
        for r in bugs_rows:
            r["bug_id"] = r.get("id")

        session.run("""
            UNWIND $rows AS row
            MERGE (b:Bug {bug_id: row.bug_id})
            SET b += row
        """, rows=bugs_rows)
        log_write(log_fh, f"[NEO4J][BUG] Stored/updated {len(bugs_rows)} bugs from bugs_with_labels.csv")

        # --- Bug–Topic (HAS_TOPIC) ---
        prepared = []
        for r in bugs_rows:
            bug_id = r.get("id")
            topic_id = r.get("topic_id") or r.get("dominant_topic")
            score = r.get("topic_score")

            if not bug_id or topic_id in (None, ""):
                continue

            try:
                topic_id = int(topic_id)
            except Exception:
                continue

            try:
                w = float(score)
            except Exception:
                w = 1.0

            prepared.append({
                "bug_id": bug_id,
                "topic_id": topic_id,
                "weight": w,
            })

        if prepared:
            session.run("""
                UNWIND $rows AS row
                MATCH (b:Bug {bug_id: row.bug_id})
                MATCH (t:Topic {topic_id: row.topic_id})
                MERGE (b)-[r:HAS_TOPIC]->(t)
                SET r.weight = row.weight
            """, rows=prepared)
            log_write(log_fh, f"[NEO4J][BUG_TOPIC] Stored {len(prepared)} HAS_TOPIC relations")
        else:
            log_write(log_fh, "[NEO4J][BUG_TOPIC] No bug-topic mapping found in bugs_with_labels.csv")
    else:
        log_write(
            log_fh,
            f"[NEO4J][BUG] bugs_with_labels.csv (path={bugs_path}) not found or empty — skip Bug nodes."
        )


def import_bug_bug(session, csv_path: str, log_write, log_fh):
    """
    Import:
      - Topic nodes (topics_cleaned.csv)
      - Bug nodes (bugs_with_labels.csv)
      - Bug–Topic relations (HAS_TOPIC)
      - Bug–Bug relations (SIMILAR_TO / DUPLICATE_OF / DEPENDS_ON)
    """
    csv_path = Path(csv_path).resolve()
    in_lda = csv_path.parent

    # 1) Pastikan Topics, Bugs, Bug-Topic masuk
    _import_topics_and_bugs(session, in_lda, log_write, log_fh)

    # 2) Bug–Bug relations
    rows = load_csv(csv_path)
    if not rows:
        log_write(log_fh, "[NEO4J][BUG_BUG] bug_bug_relations.csv empty — skip.")
        return

    prepared_by_type = {"SIMILAR_TO": [], "DUPLICATE_OF": [], "DEPENDS_ON": []}

    for r in rows:
        src = r.get("bug_id_source")
        tgt = r.get("bug_id_target")
        rel = (r.get("relation") or "").lower()
        score = r.get("score")
        source = r.get("source")

        if not src or not tgt:
            continue

        if rel == "similar":
            rel_type = "SIMILAR_TO"
        elif rel in ("duplicate", "dupe", "dup"):
            rel_type = "DUPLICATE_OF"
        elif "depend" in rel:
            rel_type = "DEPENDS_ON"
        else:
            rel_type = "NONE"

        try:
            s = float(score)
        except Exception:
            s = None

        prepared_by_type[rel_type].append({
            "src": src,
            "tgt": tgt,
            "score": s,
            "source": source,
        })

    total = 0
    for rel_type, rel_rows in prepared_by_type.items():
        if not rel_rows:
            continue
        query = f"""
        UNWIND $rows AS row
        MATCH (b1:Bug {{bug_id: row.src}})
        MATCH (b2:Bug {{bug_id: row.tgt}})
        MERGE (b1)-[r:{rel_type}]->(b2)
        SET r.score = row.score,
            r.source = row.source
        """
        session.run(query, rows=rel_rows)
        log_write(log_fh, f"[NEO4J][BUG_BUG] Stored {len(rel_rows)} {rel_type} relations")
        total += len(rel_rows)

    log_write(log_fh, f"[NEO4J][BUG_BUG] Total bug-bug relations stored: {total}")


# ============================================================
# BUG–DEVELOPER
# ============================================================

def neo4j_has_bug_developer(session):
    result = session.run("""
        MATCH (:Bug)-[r:REPORTED_BY|ASSIGNED_TO]->(:Developer)
        RETURN count(r) AS c
    """)
    rec = result.single()
    return rec and rec["c"] > 0


def import_bug_developer(session, csv_path: str, log_write, log_fh):
    csv_path = Path(csv_path).resolve()
    in_lda = csv_path.parent

    rows = load_csv(csv_path) or []

    log_write(
        log_fh,
        f"[NEO4J][BUG_DEV][DEBUG] load_csv({csv_path}) -> {len(rows)} rows"
    )

    if not rows:
        if not csv_path.exists():
            log_write(
                log_fh,
                f"[NEO4J][BUG_DEV] bug_developer_relations.csv NOT FOUND (path={csv_path}) — skip."
            )
        else:
            log_write(
                log_fh,
                f"[NEO4J][BUG_DEV] bug_developer_relations.csv EMPTY (0 rows) (path={csv_path}) — skip."
            )
        return

    # OPTIONAL: kalau ada developers.csv, import properti tambahan
    developers_csv = in_lda / "developers.csv"
    dev_rows = load_csv(developers_csv) or []
    log_write(
        log_fh,
        f"[NEO4J][BUG_DEV][DEBUG] load_csv({developers_csv}) -> {len(dev_rows)} rows"
    )

    if dev_rows:
        for r in dev_rows:
            dev_id = r.get("dev_id") or r.get("developer_id") or r.get("email")
            r["dev_id"] = dev_id
        session.run("""
            UNWIND $rows AS row
            MERGE (d:Developer {dev_id: row.dev_id})
            SET d += row
        """, rows=dev_rows)
        log_write(log_fh, f"[NEO4J][DEV] Stored/updated {len(dev_rows)} developers from developers.csv")

    # Pastikan Developer node minimal dari relasi
    session.run("""
        UNWIND $rows AS row
        MERGE (d:Developer {dev_id: row.developer_id})
        ON CREATE SET d.source = row.source
    """, rows=rows)
    log_write(log_fh, "[NEO4J][DEV] Ensured Developer nodes from bug_developer_relations.csv")

    # Buat relasi BUG–DEVELOPER
    prepared = []
    for r in rows:
        bug_id = r.get("bug_id")
        dev_id = r.get("developer_id")
        role   = (r.get("role") or "").lower()
        source = r.get("source")

        if not bug_id or not dev_id:
            continue

        if role == "creator":
            rel_type = "REPORTED_BY"
        elif role in ("assigned_to", "assignee"):
            rel_type = "ASSIGNED_TO"
        else:
            rel_type = "NONE"

        prepared.append({
            "bug_id": bug_id,
            "dev_id": dev_id,
            "rel_type": rel_type,
            "role": role,
            "source": source,
        })

    by_type = {}
    for row in prepared:
        by_type.setdefault(row["rel_type"], []).append(row)

    total = 0
    for rel_type, rel_rows in by_type.items():
        query = f"""
        UNWIND $rows AS row
        MATCH (b:Bug {{bug_id: row.bug_id}})
        MATCH (d:Developer {{dev_id: row.dev_id}})
        MERGE (b)-[r:{rel_type}]->(d)
        SET r.role = row.role,
            r.source = row.source
        """
        session.run(query, rows=rel_rows)
        log_write(log_fh, f"[NEO4J][BUG_DEV] Stored {len(rel_rows)} {rel_type} relations")
        total += len(rel_rows)

    log_write(log_fh, f"[NEO4J][BUG_DEV] Total bug-developer relations stored: {total}")


# ============================================================
# BUG–COMMIT
# ============================================================

def neo4j_has_bug_commit(session):
    result = session.run("""
        MATCH (:Bug)-[r:FIXED_BY]->(:Commit)
        RETURN count(r) AS c
    """)
    rec = result.single()
    return rec and rec["c"] > 0


def import_bug_commit(session, csv_path: str, log_write, log_fh):
    in_lda = Path(csv_path).parent

    # --- PARSE bug_commit_relations.csv secara manual ---
    path = Path(csv_path)
    if not path.exists():
        log_write(log_fh, "[NEO4J][BUG_COMMIT] bug_commit_relations.csv not found — skip.")
        return

    rows = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        # baca & buang header
        header = f.readline().strip()

        for lineno, line in enumerate(f, start=2):
            line = line.rstrip("\n")
            if not line:
                continue

            parts = line.split(",")

            if len(parts) < 4:
                log_write(
                    log_fh,
                    f"[NEO4J][BUG_COMMIT][WARN] line {lineno} malformed (expected >=4 cols): {line}",
                )
                continue

            # 4 kolom pertama sesuai header:
            # bug_id, commit_id, source, raw_value
            bug_id    = parts[0]
            commit_id = parts[1]
            source    = parts[2]
            raw_value = parts[3]

            extras = parts[4:]  # bisa kosong, 1 elemen (' a=testonly'), atau 2 elemen (msg + flag)

            message = None
            flag    = None

            if extras:
                last = extras[-1].strip()
                if last.startswith("a="):
                    flag = last
                    if len(extras) > 1:
                        message = ",".join(extras[:-1]).strip()
                else:
                    message = ",".join(extras).strip()

            rows.append({
                "bug_id": bug_id,
                "commit_id": commit_id,
                "source": source,
                "raw_value": raw_value,
                "message": message,
                "flag": flag,
            })

    if not rows:
        log_write(log_fh, "[NEO4J][BUG_COMMIT] bug_commit_relations.csv no valid rows — skip.")
        return

    # OPTIONAL: Commit metadata dari commits.csv (kalau ada)
    commits_csv = in_lda / "commits.csv"
    commit_rows = load_csv(commits_csv) or []
    if commit_rows:
        for r in commit_rows:
            cid = r.get("commit_id") or r.get("hash")
            r["commit_id"] = cid
        session.run("""
            UNWIND $rows AS row
            MERGE (c:Commit {commit_id: row.commit_id})
            SET c += row
        """, rows=commit_rows)
        log_write(log_fh, f"[NEO4J][COMMIT] Stored/updated {len(commit_rows)} commits from commits.csv")

    # Minimal commit node dari bug_commit_relations
    session.run("""
        UNWIND $rows AS row
        MERGE (c:Commit {commit_id: row.commit_id})
        ON CREATE SET c.source    = row.source,
                      c.raw_value = row.raw_value,
                      c.message   = row.message,
                      c.flag      = row.flag
        ON MATCH SET  c.last_source = row.source
    """, rows=rows)

    # Relasi Bug–Commit
    session.run("""
        UNWIND $rows AS row
        MATCH (b:Bug {bug_id: row.bug_id})
        MATCH (c:Commit {commit_id: row.commit_id})
        MERGE (b)-[r:FIXED_BY]->(c)
        SET r.source    = row.source,
            r.raw_value = row.raw_value,
            r.message   = row.message,
            r.flag      = row.flag
    """, rows=rows)

    log_write(log_fh, f"[NEO4J][BUG_COMMIT] Stored {len(rows)} bug-commit FIXED_BY relations")


# ============================================================
# COMMIT–COMMIT
# ============================================================

def neo4j_has_commit_commit(session):
    result = session.run("""
        MATCH (:Commit)-[r:RELATED_COMMIT]->(:Commit)
        RETURN count(r) AS c
    """)
    rec = result.single()
    return rec and rec["c"] > 0


def import_commit_commit(session, csv_path: str, log_write, log_fh):
    path = Path(csv_path)
    if not path.exists():
        log_write(log_fh, "[NEO4J][COMMIT_COMMIT] commit_commit_relations.csv not found — skip.")
        return

    rows = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        # baca header, tapi kita parse manual baris-baris berikutnya
        header = f.readline().strip()

        for lineno, line in enumerate(f, start=2):
            line = line.rstrip("\n")
            if not line:
                continue

            parts = line.split(",")

            if len(parts) < 5:
                log_write(
                    log_fh,
                    f"[NEO4J][COMMIT_COMMIT][WARN] line {lineno} malformed (expected >=5 cols): {line}",
                )
                continue

            # pola: [src] [..... target .....] [relation] [score] [source]
            commit_id_source = parts[0]
            relation         = parts[-3]
            score_str        = parts[-2]
            source           = parts[-1]

            # semua yang di tengah digabung lagi jadi 1 string
            commit_id_target = ",".join(parts[1:-3])

            try:
                score = float(score_str)
            except Exception:
                score = None

            rows.append({
                "commit_id_source": commit_id_source,
                "commit_id_target": commit_id_target,
                "relation": relation,
                "score": score,
                "source": source,
            })

    if not rows:
        log_write(log_fh, "[NEO4J][COMMIT_COMMIT] no valid rows — skip.")
        return

    session.run("""
        UNWIND $rows AS row
        MERGE (c1:Commit {commit_id: row.commit_id_source})
        MERGE (c2:Commit {commit_id: row.commit_id_target})
        MERGE (c1)-[r:RELATED_COMMIT]->(c2)
        SET r.score   = row.score,
            r.source  = row.source,
            r.relation = row.relation
    """, rows=rows)

    log_write(log_fh, f"[NEO4J][COMMIT_COMMIT] Stored {len(rows)} commit-commit relations")


# ============================================================
# MAIN PIPELINE
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Store LDA relations to Neo4j (robust)")
    parser.add_argument("--in_lda", type=str, default=os.getenv("PATH_LDA_OUT", "out_lda"))
    parser.add_argument("--neo4j-uri", type=str, default=os.getenv("NEO4J_URI", "bolt://localhost:7687"))
    parser.add_argument("--neo4j-user", type=str, default=os.getenv("NEO4J_USER", "neo4j"))
    parser.add_argument("--neo4j-pass", type=str, default=os.getenv("NEO4J_PASS", "password"))
    parser.add_argument("--neo4j-db", type=str, default=None)
    parser.add_argument("--log_path", type=str, default=None)
    args = parser.parse_args()

    main_mod = get_main_module()
    log_fh = None
    log_write = print
    if main_mod and hasattr(main_mod, "log_write"):
        log_write = main_mod.log_write

    if args.log_path:
        try:
            log_fh = open(args.log_path, "a", encoding="utf-8")
        except Exception:
            log_fh = None

    db_name = args.neo4j_db or os.getenv("NEO4J_DB") or "neo4j"
    log_write(log_fh, "[NEO4J] === Store to database started ===")
    log_write(log_fh, f"[NEO4J] using database: {db_name}")

    # normalisasi in_lda jadi Path absolut
    args.in_lda = Path(args.in_lda)
    if not args.in_lda.is_absolute():
        args.in_lda = (Path(__file__).resolve().parent / args.in_lda).resolve()

    exists = args.in_lda.exists()
    is_dir = args.in_lda.is_dir()
    log_write(
        log_fh,
        f"[NEO4J] Using LDA directory: {args.in_lda} (exists={exists}, is_dir={is_dir})"
    )

    # Jangan langsung exit, biarkan cek per-file yang menangani
    if not exists:
        log_write(
            log_fh,
            f"[NEO4J][WARN] LDA output path does not exist yet (path={args.in_lda}); "
            "file-level checks will handle missing files."
        )
    elif not is_dir:
        log_write(
            log_fh,
            f"[NEO4J][WARN] LDA path exists but is not a directory (path={args.in_lda}); "
            "file-level checks will handle missing files."
        )

    # connect
    try:
        driver = neo4j_connect(args.neo4j_uri, args.neo4j_user, args.neo4j_pass, db_name=db_name)
    except RuntimeError as e:
        log_write(log_fh, f"[NEO4J][ERROR] {e}")
        sys.exit(1)

    # constraints
    with driver.session(database=db_name) as session:
        session.run("""
            CREATE CONSTRAINT bug_bug_id_unique
            IF NOT EXISTS
            ON (b:Bug)
            ASSERT b.bug_id IS UNIQUE
        """)

        session.run("""
            CREATE CONSTRAINT dev_dev_id_unique
            IF NOT EXISTS
            ON (d:Developer)
            ASSERT d.dev_id IS UNIQUE
        """)

        session.run("""
            CREATE CONSTRAINT commit_commit_id_unique
            IF NOT EXISTS
            ON (c:Commit)
            ASSERT c.commit_id IS UNIQUE
        """)

        log_write(log_fh, "[NEO4J] constraints ensured")

    # imports
    with driver.session(database=db_name) as session:
        # 1) bug-bug
        p = args.in_lda / "bug_bug_relations.csv"
        if neo4j_has_bug_bug(session):
            log_write(log_fh, "[NEO4J] bug-bug relations already exist — skip.")
        elif p.exists():
            import_bug_bug(session, str(p), log_write, log_fh)
        else:
            log_write(log_fh, f"[NEO4J] bug_bug_relations.csv (path={p}) not found — skip.")

        # 2) bug-developer
        p = args.in_lda / "bug_developer_relations.csv"
        if neo4j_has_bug_developer(session):
            log_write(log_fh, "[NEO4J] bug-developer relations already exist — skip.")
        elif p.exists():
            import_bug_developer(session, str(p), log_write, log_fh)
        else:
            log_write(log_fh, f"[NEO4J] bug_developer_relations.csv (path={p}) not found — skip.")

        # 3) bug-commit
        p = args.in_lda / "bug_commit_relations.csv"
        if neo4j_has_bug_commit(session):
            log_write(log_fh, "[NEO4J] bug-commit relations already exist — skip.")
        elif p.exists():
            import_bug_commit(session, str(p), log_write, log_fh)
        else:
            log_write(log_fh, f"[NEO4J] bug_commit_relations.csv (path={p}) not found — skip.")

        # 4) commit-commit
        p = args.in_lda / "commit_commit_relations.csv"
        if neo4j_has_commit_commit(session):
            log_write(log_fh, "[NEO4J] commit-commit relations already exist — skip.")
        elif p.exists():
            import_commit_commit(session, str(p), log_write, log_fh)
        else:
            log_write(log_fh, f"[NEO4J] commit_commit_relations.csv (path={p}) not found — skip.")

    driver.close()
    log_write(log_fh, "[NEO4J] === Store to database finished ===")

    if args.log_path and log_fh:
        try:
            log_fh.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
