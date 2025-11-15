#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
02_lda_topics.py  (cleaned)
- Read CSV from 01_nlp_preprocess.py (bugs_clean.csv)
- Train LDA (sklearn)
- Export:
    1) topics.csv
    2) bugs_with_topics.csv
    3) bug_bug_relations.csv
    4) bug_developer_relations.csv
    5) bug_commit_relations.csv
    6) commit_commit_relations.csv
"""

import os, argparse, warnings, sys, datetime, importlib.util, re
from typing import List, Set

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.decomposition import LatentDirichletAllocation
from sklearn.model_selection import train_test_split
from sklearn.neighbors import NearestNeighbors

warnings.filterwarnings("ignore", category=FutureWarning)

# --- load .env ---

HERE = os.path.dirname(os.path.abspath(__file__))
def load_env():
    # 1) coba python-dotenv
    loaded = False
    try:
        from dotenv import load_dotenv
        # coba yang CWD
        load_dotenv()
        # coba yang lokasi file ini
        load_dotenv(os.path.join(HERE, ".env"))
        loaded = True
    except Exception:
        loaded = False

    # 2) kalau gak ada python-dotenv, baca manual
    if not loaded:
        env_path = os.path.join(HERE, ".env")
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip()
                    os.environ.setdefault(k, v)

load_env()

DEFAULT_SIM_THRESHOLD = 0.60
DEFAULT_DUP_THRESHOLD = 0.80


# -------- load main.py ------
def get_main_module():
    """Dynamically load main.py so we can reuse its log_write()."""
    here = os.path.dirname(os.path.abspath(__file__))
    main_path = os.path.join(here, "main.py")
    if not os.path.exists(main_path):
        return None
    spec = importlib.util.spec_from_file_location("main_module", main_path)
    main_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(main_mod)
    return main_mod


# ---------------------------- Core training ---------------------------- #

def _build_vectorizer():
    # clean_text sudah dipreproses; tokenisasi per kata
    return CountVectorizer(
        max_df=0.5,
        min_df=3,
        token_pattern=r"(?u)\b\w+\b"
    )


def _fit_lda(X, n_components=10, max_iter=12, random_state=42):
    lda = LatentDirichletAllocation(
        n_components=n_components,
        max_iter=max_iter,
        learning_method="batch",
        random_state=random_state,
        evaluate_every=-1,
    )
    lda.fit(X)
    return lda


def _choose_k_auto(X, base_k=10, max_iter=12, random_state=42):
    """pilih K dengan perplexity di holdout"""
    X_train, X_val = train_test_split(X, test_size=0.2, random_state=random_state, shuffle=True)
    ks = list(range(max(3, base_k - 4), base_k + 5))
    best_k, best_ppx, best_model = None, float("inf"), None
    for k in ks:
        lda = _fit_lda(X_train, n_components=k, max_iter=max_iter, random_state=random_state)
        total_words = X_val.sum()
        ppx = np.exp(-lda.score(X_val) / total_words) if total_words > 0 else np.inf
        if ppx < best_ppx:
            best_k, best_ppx, best_model = k, ppx, lda
    return best_model, best_k


def train_lda_sklearn(texts, num_topics=10, passes=12, auto_k=False, random_state=42):
    vectorizer = _build_vectorizer()
    X = vectorizer.fit_transform(texts)
    if auto_k:
        lda_model, chosen_k = _choose_k_auto(X, base_k=num_topics, max_iter=passes, random_state=random_state)
    else:
        lda_model = _fit_lda(X, n_components=num_topics, max_iter=passes, random_state=random_state)
        chosen_k = num_topics
    doc_topic = lda_model.transform(X).astype(np.float32)
    vocab = vectorizer.get_feature_names_out()
    return lda_model, vocab, doc_topic, chosen_k


# ---------------------------- Exports ---------------------------- #

def export_topics_sklearn(lda_model, vocab, outdir, topn=12):
    rows = []
    comps = lda_model.components_
    for k, topic_vec in enumerate(comps):
        top_idx = topic_vec.argsort()[:-topn-1:-1]
        terms = [str(vocab[i]) for i in top_idx]
        rows.append({"topic_id": k, "terms": ", ".join(terms)})
    pd.DataFrame(rows).to_csv(os.path.join(outdir, "topics.csv"), index=False)


def export_bug_table(df, topic_mat, outdir):
    dom_topic = topic_mat.argmax(axis=1)
    dom_score = topic_mat.max(axis=1)
    out = df.copy()
    out["dominant_topic"] = dom_topic
    out["topic_score"] = np.round(dom_score, 4)
    out.to_csv(os.path.join(outdir, "bugs_with_topics.csv"), index=False)


# ---------------------------- Relation helpers ---------------------------- #

def _split_semicolon(val) -> List[str]:
    if pd.isna(val) or val is None:
        return []
    if isinstance(val, float):
        return []
    return [x.strip() for x in str(val).split(";") if x.strip()]


def export_bug_bug_relations(df: pd.DataFrame,
                             topic_mat: np.ndarray,
                             sim_th: float,
                             dup_th: float,
                             outdir: str,
                             chunk_flush: int = 100_000):
    """
    (1) LDA-based similarity (similar / duplicate)
    (2) Explicit deps dari kolom 'depends_on' -> relation 'depends_on'
    """
    topic_mat = np.asarray(topic_mat, dtype=np.float32)
    radius = 1.0 - float(sim_th)  # cosine distance radius
    nbrs = NearestNeighbors(metric="cosine", radius=radius, algorithm="brute", n_jobs=-1)
    nbrs.fit(topic_mat)
    G = nbrs.radius_neighbors_graph(topic_mat, mode="distance").tocsr()
    G.data = 1.0 - G.data  # distance -> similarity

    ids = df["id"].to_numpy() if "id" in df.columns else np.arange(len(df))
    out_path = os.path.join(outdir, "bug_bug_relations.csv")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("bug_id_source,bug_id_target,score,relation,source\n")

    buf = []
    rows, cols = G.nonzero()
    data = G.data
    for i, j, s in zip(rows, cols, data):
        if j <= i:
            continue
        relation = "duplicate" if s >= dup_th else "similar"
        buf.append(f"{int(ids[i])},{int(ids[j])},{s:.4f},{relation},lda_radius")
        if len(buf) >= chunk_flush:
            with open(out_path, "a", encoding="utf-8") as f:
                f.write("\n".join(buf) + "\n")
            buf.clear()

    # explicit depends_on dari file NLP
    if "depends_on" in df.columns:
        for _, row in df.iterrows():
            src_id = row.get("id")
            if pd.isna(src_id):
                continue
            for dep in _split_semicolon(row["depends_on"]):
                try:
                    dep_id = int(dep)
                except ValueError:
                    continue
                buf.append(f"{int(src_id)},{dep_id},1.0000,depends_on,bugzilla_field")

    if buf:
        with open(out_path, "a", encoding="utf-8") as f:
            f.write("\n".join(buf) + "\n")


def export_bug_developer_relations(df: pd.DataFrame, outdir: str):
    out_path = os.path.join(outdir, "bug_developer_relations.csv")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("bug_id,developer_id,role,source\n")

    rows = []
    for _, row in df.iterrows():
        bug_id = int(row["id"]) if "id" in row and not pd.isna(row["id"]) else None
        if bug_id is None:
            continue

        creator = row.get("creator")
        if isinstance(creator, str) and creator.strip():
            rows.append(f"{bug_id},{creator.strip()},creator,bug_fields")

        assigned = row.get("assigned_to")
        if isinstance(assigned, str) and assigned.strip():
            rows.append(f"{bug_id},{assigned.strip()},assigned_to,bug_fields")

    if rows:
        with open(out_path, "a", encoding="utf-8") as f:
            f.write("\n".join(rows) + "\n")


_commit_rev_regex = re.compile(r"/rev/([0-9a-fA-F]+)$")

def _normalize_commit_id(val: str) -> str:
    if not isinstance(val, str):
        return ""
    val = val.strip()
    if not val:
        return ""
    m = _commit_rev_regex.search(val)
    if m:
        return m.group(1)
    if re.fullmatch(r"[0-9a-fA-F]{7,40}", val):
        return val
    return val.replace(" ", "_")


def export_bug_commit_relations(df: pd.DataFrame, outdir: str):
    """
    bug -> commit_id dari:
      - commit_refs (URL / hash)
      - commit_messages (dibikin pseudo id)
      - files_changed (dibikin pseudo id)
    """
    out_path = os.path.join(outdir, "bug_commit_relations.csv")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("bug_id,commit_id,source,raw_value\n")

    rows = []
    for _, row in df.iterrows():
        bug_id = int(row["id"]) if "id" in row and not pd.isna(row["id"]) else None
        if bug_id is None:
            continue

        # 1) commit_refs
        for c in _split_semicolon(row.get("commit_refs")):
            cid = _normalize_commit_id(c)
            if cid:
                rows.append(f"{bug_id},{cid},commit_refs,{c}")

        # 2) commit_messages
        for m in _split_semicolon(row.get("commit_messages")):
            cid = "msg_" + _normalize_commit_id(m[:50])
            rows.append(f"{bug_id},{cid},commit_messages,{m}")

        # 3) files_changed
        for file_path in _split_semicolon(row.get("files_changed")):
            cid = "file_" + _normalize_commit_id(file_path)
            rows.append(f"{bug_id},{cid},files_changed,{file_path}")

    if rows:
        with open(out_path, "a", encoding="utf-8") as f:
            f.write("\n".join(rows) + "\n")


def export_commit_commit_relations(df: pd.DataFrame, outdir: str):
    """
    commit-commit co-occurs:
    kalau 2 commit muncul di 1 bug yang sama → relasi
    """
    out_path = os.path.join(outdir, "commit_commit_relations.csv")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("commit_id_source,commit_id_target,relation,score,source\n")

    buf = []
    for _, row in df.iterrows():
        commits: Set[str] = set()
        for src_col in ("commit_refs", "commit_messages", "files_changed"):
            for item in _split_semicolon(row.get(src_col)):
                if src_col == "commit_refs":
                    cid = _normalize_commit_id(item)
                elif src_col == "commit_messages":
                    cid = "msg_" + _normalize_commit_id(item[:50])
                else:
                    cid = "file_" + _normalize_commit_id(item)
                if cid:
                    commits.add(cid)

        commits = sorted(commits)
        for i in range(len(commits)):
            for j in range(i + 1, len(commits)):
                c1 = commits[i]
                c2 = commits[j]
                buf.append(f"{c1},{c2},co_occurs,1.0,bug_row")

    if buf:
        with open(out_path, "a", encoding="utf-8") as f:
            f.write("\n".join(buf) + "\n")


# ---------------------------- CLI ---------------------------- #

def main():
    # ambil default dari .env supaya align dengan main.py kamu
    nlp_dir_default = os.getenv("PATH_NLP_OUT", "out_nlp")

    parser = argparse.ArgumentParser(description="LDA topic modeling for EasyFix (scikit-learn)")
    parser.add_argument("--input", type=str, default=os.path.join(nlp_dir_default, "bugs_clean.csv"))
    parser.add_argument("--outdir", type=str, default=os.getenv("PATH_LDA_OUT", "out_lda"))
    parser.add_argument("--num_topics", type=int, default=int(os.getenv("NUM_TOPICS", "10")))
    parser.add_argument("--passes", type=int, default=int(os.getenv("PASSES", "12")))
    parser.add_argument("--auto_k", action="store_true")
    parser.add_argument("--topn_terms", type=int, default=12)
    parser.add_argument("--sim_threshold", type=float, default=float(os.getenv("SIM_THRESHOLD", str(DEFAULT_SIM_THRESHOLD))))
    parser.add_argument("--dup_threshold", type=float, default=float(os.getenv("DUP_THRESHOLD", str(DEFAULT_DUP_THRESHOLD))))
    parser.add_argument("--log_path", type=str, default=None)
    args = parser.parse_args()

    os.makedirs(args.outdir, exist_ok=True)

    # --- init logging ---
    main_mod = get_main_module()
    log_fh = None
    log_write = print  # fallback

    if main_mod and hasattr(main_mod, "log_write"):
        log_write = main_mod.log_write
        if args.log_path:
            try:
                log_fh = open(args.log_path, "a", encoding="utf-8")
            except Exception as e:
                print(f"[WARN] Could not open log file: {e}")
        else:
            # fallback kalau dipanggil langsung
            date_str = datetime.datetime.now().strftime("%Y-%m-%d")
            log_path = os.path.join(os.getcwd(), f"log_{date_str}.txt")
            try:
                log_fh = open(log_path, "a", encoding="utf-8")
            except Exception as e:
                print(f"[WARN] Could not open default log: {e}")

    log_write(log_fh, f"[LDA] === Starting LDA ===")
    log_write(log_fh, f"[LDA] input={args.input} outdir={args.outdir} num_topics={args.num_topics}")

    df = pd.read_csv(args.input)
    if "clean_text" not in df.columns:
        log_write(log_fh, "[LDA][ERROR] Missing 'clean_text' column")
        sys.exit(1)

    texts = df["clean_text"].fillna("").astype(str).tolist()

    log_write(log_fh, "[LDA] Training model…")
    lda_model, vocab, topic_mat, chosen_k = train_lda_sklearn(
        texts, args.num_topics, args.passes, args.auto_k, random_state=42
    )
    log_write(log_fh, f"[LDA] Model trained. num_topics={chosen_k}")

    log_write(log_fh, "[LDA] Exporting topics & tables…")
    export_topics_sklearn(lda_model, vocab, args.outdir, args.topn_terms)
    export_bug_table(df, topic_mat, args.outdir)

    log_write(log_fh, "[LDA] Exporting relation CSVs…")
    export_bug_bug_relations(df, topic_mat, args.sim_threshold, args.dup_threshold, args.outdir)
    export_bug_developer_relations(df, args.outdir)
    export_bug_commit_relations(df, args.outdir)
    export_commit_commit_relations(df, args.outdir)

    # save model meta
    np.savez(os.path.join(args.outdir, "lda_sklearn_model_meta.npz"),
             components=lda_model.components_,
             vocab=vocab,
             doc_topic=topic_mat)

    log_write(log_fh, "[LDA] === Finished successfully ===")
    # biarkan main.py yg nutup, tapi kalau file ini berdiri sendiri, gapapa ditutup
    if log_fh:
        try:
            log_fh.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
