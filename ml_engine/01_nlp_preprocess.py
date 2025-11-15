#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
01_nlp_preprocess.py
- Load Bugzilla JSONL (e.g., datasource/bugs2.jsonl)
- Clean & normalize text (summary/description)
- Output a CSV with clean_text and essential metadata for later modeling.
"""

import os, re, string, json, argparse, warnings
import pandas as pd

warnings.filterwarnings("ignore", category=FutureWarning)

HERE = os.path.dirname(os.path.abspath(__file__))

# --- try load .env (biar sama dgn main.py) ---
def load_env():
    loaded = False
    try:
        from dotenv import load_dotenv
        # coba di CWD
        load_dotenv()
        # coba di folder file ini
        load_dotenv(os.path.join(HERE, ".env"))
        loaded = True
    except Exception:
        pass
    if not loaded:
        # fallback: baca manual .env di folder ini kalau ada
        env_path = os.path.join(HERE, ".env")
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

load_env()


# ---------- NLP Utilities ----------

def ensure_nltk():
    import nltk
    try:
        nltk.data.find("tokenizers/punkt")
    except LookupError:
        nltk.download("punkt")
    try:
        nltk.data.find("corpora/stopwords")
    except LookupError:
        nltk.download("stopwords")

def build_stopwords():
    from nltk.corpus import stopwords
    sw = set()
    # English & Indonesian
    try:
        sw |= set(stopwords.words("english"))
    except:
        pass
    try:
        sw |= set(stopwords.words("indonesian"))
    except:
        pass
    # Technical/common words to de-emphasize topics
    sw |= {
        "error","issue","bug","fix","fixed","problem","invalid","message","crash",
        "firefox","mozilla","general","component","please","thanks",
        "step","steps","reproduce","expected","actual"
    }
    # single letters
    for ch in "abcdefghijklmnopqrstuvwxyz":
        sw.add(ch)
    return sw

def clean_text(text, sw):
    if not isinstance(text, str):
        return ""
    text = text.lower()
    # remove URLs, git hashes, explicit bug ids, keep short path markers minimally
    text = re.sub(r"http\S+", " ", text)
    text = re.sub(r"[a-f0-9]{7,40}", " ", text)           # git hashes and similar
    text = re.sub(r"bug\s*#?\s*\d+", " ", text)           # explicit Bug IDs
    text = re.sub(r"[^\w\s\./-]+", " ", text)             # keep / . - to preserve short paths
    tokens = re.split(r"\s+", text)

    def ok(tok):
        if not tok: return False
        if tok in sw: return False
        if tok.isdigit(): return False
        if len(tok) < 3: return False
        # overly long path-ish tokens → drop
        if tok.count(".") > 3 or tok.count("/") > 3: return False
        return True

    tokens = [t.strip(string.punctuation) for t in tokens]
    tokens = [t for t in tokens if ok(t)]
    return " ".join(tokens)



# ---------- IO ----------

def load_jsonl(path):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line=line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return pd.DataFrame(rows)


def flatten_value(val):
    """
    Bugzilla new structure has list fields (commit_messages, commit_refs, files_changed, keywords, depends_on).
    This helper will make them joinable.
    """
    if val is None:
        return ""
    if isinstance(val, list):
        # convert every item to str, then join
        return " ".join(str(x) for x in val if x is not None)
    # for non-list, just cast to str
    return str(val)


def list_to_semicolon(val):
    """
    For saving into CSV: keep list columns readable.
    """
    if isinstance(val, list):
        return ";".join(str(x) for x in val)
    return val



def main():
    parser = argparse.ArgumentParser(description="NLP preprocessing for EasyFix bug reports")
    # DEFAULT_DATASOURCE diambil dari .env atau fallback
    parser.add_argument("--input", type=str, default=os.getenv("DATASOURCE", "datasource/bugs2.jsonl"), help="Path to Bugzilla JSONL")
    parser.add_argument("--outdir", type=str, default=os.getenv("PATH_NLP_OUT", "out_nlp"), help="Output directory")
    parser.add_argument(
        "--text-cols",
        type=str,
        default=os.getenv("NLP_TEXT_COLS", "summary,product,component,commit_messages,files_changed"),
        help="Comma-separated text columns to merge & clean"
    )
    args = parser.parse_args()

    os.makedirs(args.outdir, exist_ok=True)

    print(f"[NLP] Loading: {args.input}")
    df = load_jsonl(args.input)

    base_cols = [
        "id",
        "summary",
        "creator",
        "assigned_to",
        "status",
        "resolution",
        "creation_time",
        "last_change_time",
        # new fields from your example
        "product",
        "component",
        "keywords",
        "depends_on",
        "dupe_of",
        "commit_messages",
        "commit_refs",
        "files_changed",
        "url",
    ]
    
    # Ensure key cols exist
    for col in base_cols:
        if col not in df.columns:
            df[col] = None

    ensure_nltk()
    sw = build_stopwords()

    text_cols = [c.strip() for c in args.text_cols.split(",") if c.strip()]
    if not text_cols:
        text_cols = ["summary"]

    clean_texts = []
    for _, row in df.iterrows():
        chunks = []
        for c in text_cols:
            if c not in df.columns:
                continue
            val = row.get(c)
            if val is None:
                continue
            # handle list vs string
            if isinstance(val, str):
                if val.strip():
                    chunks.append(val)
            elif isinstance(val, list):
                flat = flatten_value(val)
                if flat.strip():
                    chunks.append(flat)
            else:
                flat = str(val)
                if flat.strip():
                    chunks.append(flat)

        # fallback: at least summary
        if not chunks and isinstance(row.get("summary"), str):
            chunks = [row.get("summary")]

        raw = " ".join(chunks)
        clean_texts.append(clean_text(raw, sw))

    out = df.copy()
    out["clean_text"] = clean_texts

    # convert list-ish cols so CSV tetap enak dibaca
    for col in ["keywords", "depends_on", "commit_messages", "commit_refs", "files_changed"]:
        if col in out.columns:
            out[col] = out[col].apply(list_to_semicolon)

    # Save a compact modeling table
    cols = [
        "id",
        "clean_text",
        "summary",
        "product",
        "component",
        "creator",
        "assigned_to",
        "status",
        "resolution",
        "creation_time",
        "last_change_time",
        "keywords",
        "depends_on",
        "dupe_of",
        "commit_messages",
        "commit_refs",
        "files_changed",
        "url",
    ]
    for c in cols:
        if c not in out.columns:
            out[c] = None

    out_path = os.path.join(args.outdir, "bugs_clean.csv")
    out[cols].to_csv(out_path, index=False)
    print(f"[NLP] Wrote {out_path}")

if __name__ == "__main__":
    main()
