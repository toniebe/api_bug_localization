#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
02_lda_topics.py  (gensim version)
- Read CSV from 01_nlp_preprocess.py (bugs_clean.csv)
- Train LDA (gensim)
- Export:
    1) topics.csv
    2) bugs_with_topics.csv
    3) bug_bug_relations.csv
    4) bug_developer_relations.csv
    5) bug_commit_relations.csv
    6) commit_commit_relations.csv
    7) commits.csv
"""

import os, argparse, warnings, sys, datetime, importlib.util, re
from typing import List, Set

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.neighbors import NearestNeighbors

from gensim import corpora, models

from lda_config import resolve_lda_params

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


# ---------------------------- Core training (gensim) ---------------------------- #

def _tokenize_clean_text(texts: List[str]) -> List[List[str]]:
    """
    clean_text sudah dipreproses (spasi antar token).
    Kita cukup split per spasi.
    """
    return [str(t).split() for t in texts]


def _build_dictionary(tokenized_docs: List[List[str]]):
    """
    Mirip CountVectorizer(max_df=0.5, min_df=3):
    - no_below=3  (muncul di >=3 dokumen)
    - no_above=0.5 (muncul di <= 50% dokumen)
    """
    dictionary = corpora.Dictionary(tokenized_docs)
    dictionary.filter_extremes(no_below=3, no_above=0.5)
    dictionary.compactify()
    return dictionary


def _build_corpus(dictionary, tokenized_docs):
    return [dictionary.doc2bow(doc) for doc in tokenized_docs]


def _fit_lda_gensim(corpus, dictionary, num_topics=10, passes=12, random_state=42):
    """
    Train LDA menggunakan gensim.models.LdaModel.
    """
    lda_model = models.LdaModel(
        corpus=corpus,
        id2word=dictionary,
        num_topics=num_topics,
        passes=passes,
        random_state=random_state,
        eval_every=None,
    )
    return lda_model


def _doc_topic_matrix(lda_model, corpus, num_topics: int) -> np.ndarray:
    """
    Konversi distribusi topic tiap dokumen ke bentuk dense matrix:
    shape = (n_docs, num_topics)
    """
    n_docs = len(corpus)
    mat = np.zeros((n_docs, num_topics), dtype=np.float32)
    for i, bow in enumerate(corpus):
        doc_topics = lda_model.get_document_topics(bow, minimum_probability=0.0)
        for tid, prob in doc_topics:
            mat[i, tid] = prob
    return mat


def train_lda_gensim(texts, num_topics=10, passes=12, auto_k=False, random_state=42):
    """
    Wrapper utama untuk training LDA dengan gensim.
    auto_k saat ini diabaikan (param num_topics sudah ditentukan oleh resolve_lda_params).
    """
    tokenized_docs = _tokenize_clean_text(texts)
    dictionary = _build_dictionary(tokenized_docs)
    corpus = _build_corpus(dictionary, tokenized_docs)

    lda_model = _fit_lda_gensim(
        corpus=corpus,
        dictionary=dictionary,
        num_topics=num_topics,
        passes=passes,
        random_state=random_state,
    )
    topic_mat = _doc_topic_matrix(lda_model, corpus, num_topics)
    chosen_k = num_topics
    return lda_model, dictionary, topic_mat, chosen_k


# ---------------------------- Exports ---------------------------- #

def export_topics_gensim(lda_model, dictionary, outdir, topn=12):
    """
    Export top terms per topic ke topics.csv menggunakan gensim LdaModel.
    """
    rows = []
    num_topics = lda_model.num_topics
    for k in range(num_topics):
        topic_terms = lda_model.get_topic_terms(k, topn=topn)
        terms = [dictionary[tid] for tid, _ in topic_terms]
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


def export_bug_bug_relations(
    df: pd.DataFrame,
    topic_mat: np.ndarray,
    sim_th: float,
    dup_th: float,
    outdir: str,
    chunk_flush: int = 100_000,
):
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


def export_commits_csv(df: pd.DataFrame, outdir: str):
    """
    Generate commits.csv (satu baris per commit_id) dengan metadata:
    - commit_refs      -> commit_ref
    - commit_messages  -> message & commit_messages
    - files_changed    -> files_changed

    commit_id HARUS konsisten dengan:
      - export_bug_commit_relations
      - export_commit_commit_relations
    """
    commits = {}

    def ensure_commit(cid: str):
        if cid not in commits:
            commits[cid] = {
                "commit_id": cid,
                "message": set(),
                "commit_messages": set(),
                "commit_ref": set(),
                "files_changed": set(),
            }
        return commits[cid]

    # iterasi semua bug row di bugs_clean.csv
    for _, row in df.iterrows():
        # 1) commit_refs -> commit_ref
        for c in _split_semicolon(row.get("commit_refs")):
            cid = _normalize_commit_id(c)
            if cid:
                rec = ensure_commit(cid)
                rec["commit_ref"].add(c)

        # 2) commit_messages -> message & commit_messages
        for m in _split_semicolon(row.get("commit_messages")):
            cid = "msg_" + _normalize_commit_id(m[:50])
            rec = ensure_commit(cid)
            rec["message"].add(m)
            rec["commit_messages"].add(m)

        # 3) files_changed -> files_changed
        for fp in _split_semicolon(row.get("files_changed")):
            cid = "file_" + _normalize_commit_id(fp)
            rec = ensure_commit(cid)
            rec["files_changed"].add(fp)

    if not commits:
        # tidak ada commit info sama sekali, skip
        return

    rows = []
    for cid, data in commits.items():
        rows.append({
            "commit_id": cid,
            "message": "; ".join(sorted(data["message"])) if data["message"] else "",
            "commit_messages": "; ".join(sorted(data["commit_messages"])) if data["commit_messages"] else "",
            "commit_ref": "; ".join(sorted(data["commit_ref"])) if data["commit_ref"] else "",
            "files_changed": "; ".join(sorted(data["files_changed"])) if data["files_changed"] else "",
        })

    commits_df = pd.DataFrame(rows)
    commits_df.to_csv(os.path.join(outdir, "commits.csv"), index=False)


def str2bool(v):
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    return str(v).lower() in ("1", "true", "yes", "on")


# ---------------------------- CLI ---------------------------- #

def main():
    # ambil default dari .env supaya align dengan main.py kamu
    nlp_dir_default = os.getenv("PATH_NLP_OUT", "out_nlp")

    parser = argparse.ArgumentParser(description="LDA topic modeling for EasyFix (gensim)")
    parser.add_argument("--input", type=str, default=os.path.join(nlp_dir_default, "bugs_clean.csv"))
    parser.add_argument("--outdir", type=str, default=os.getenv("PATH_LDA_OUT", "out_lda"))
    parser.add_argument("--auto_topics_num", type=str, default=str2bool(os.getenv("AUTO_TOPICS_NUM", "true")))
    parser.add_argument("--num_topics", type=int, default=int(os.getenv("NUM_TOPICS", "10")))
    parser.add_argument("--passes", type=int, default=int(os.getenv("PASSES", "12")))
    parser.add_argument("--auto_k", action="store_true")
    parser.add_argument("--topn_terms", type=int, default=12)
    parser.add_argument(
        "--sim_threshold",
        type=float,
        default=float(os.getenv("SIM_THRESHOLD", str(DEFAULT_SIM_THRESHOLD))),
    )
    parser.add_argument(
        "--dup_threshold",
        type=float,
        default=float(os.getenv("DUP_THRESHOLD", str(DEFAULT_DUP_THRESHOLD))),
    )
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

    log_write(log_fh, f"[LDA] === Starting LDA (gensim) ===")
    log_write(log_fh, f"[LDA] input={args.input} outdir={args.outdir} num_topics={args.num_topics}")

    df = pd.read_csv(args.input)
    if "clean_text" not in df.columns:
        log_write(log_fh, "[LDA][ERROR] Missing 'clean_text' column")
        sys.exit(1)

    texts = df["clean_text"].fillna("").astype(str).tolist()

    log_write(log_fh, "[LDA] Training model…")
    if args.auto_topics_num:
        num_topics, passes = resolve_lda_params(
            n_docs=len(texts),
            logger=log_fh,
        )
    else:
        num_topics = args.num_topics
        passes = args.passes

    log_write(log_fh, f"[LDA] NUM TOPICS : {num_topics} - PASSES : {passes} ")

    lda_model, dictionary, topic_mat, chosen_k = train_lda_gensim(
        texts, num_topics=num_topics, passes=passes, auto_k=args.auto_k, random_state=42
    )
    log_write(log_fh, f"[LDA] Model trained. num_topics={chosen_k}")
    
     # === Tambahan: simpan artefak model untuk dipakai online ===
    log_write(log_fh, "[LDA] Saving model artifacts for online inference…")
    dict_path = os.path.join(args.outdir, "lda_dictionary.dict")
    model_path = os.path.join(args.outdir, "lda_model.gensim")
    topic_mat_path = os.path.join(args.outdir, "topic_mat.npy")
    bug_ids_path = os.path.join(args.outdir, "bug_ids.txt")

    dictionary.save(dict_path)
    lda_model.save(model_path)
    np.save(topic_mat_path, topic_mat)

    # Simpan urutan bug_id yang align dengan topic_mat
    if "id" in df.columns:
        with open(bug_ids_path, "w", encoding="utf-8") as f:
            for v in df["id"].tolist():
                f.write(f"{int(v)}\n")
    else:
        with open(bug_ids_path, "w", encoding="utf-8") as f:
            for i in range(len(df)):
                f.write(f"{i}\n")
                

    log_write(log_fh, "[LDA] Exporting topics & tables…")
    export_topics_gensim(lda_model, dictionary, args.outdir, args.topn_terms)
    export_bug_table(df, topic_mat, args.outdir)

    log_write(log_fh, "[LDA] Exporting relation CSVs…")
    export_bug_bug_relations(df, topic_mat, args.sim_threshold, args.dup_threshold, args.outdir)
    export_bug_developer_relations(df, args.outdir)
    export_bug_commit_relations(df, args.outdir)
    export_commit_commit_relations(df, args.outdir)

    log_write(log_fh, "[LDA] Exporting commits.csv…")
    export_commits_csv(df, args.outdir)

    # save model meta (kompatibel dengan versi sklearn lama: components, vocab, doc_topic)
    components = lda_model.get_topics()  # shape (num_topics, vocab_size)
    vocab = np.array([dictionary[i] for i in range(len(dictionary))], dtype=object)
    np.savez(
        os.path.join(args.outdir, "lda_sklearn_model_meta.npz"),
        components=components,
        vocab=vocab,
        doc_topic=topic_mat,
    )

    log_write(log_fh, "[LDA] === Finished successfully ===")
    if log_fh:
        try:
            log_fh.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
