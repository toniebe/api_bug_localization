#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
instal dotenv
- pip install python-dotenv
- pip install neo4j

main.py
Run EasyFix step-by-step IN-PROCESS:
  1) 01_nlp_preprocess.py
  2) 02_lda_topics.py
  3) 03_clean_topics.py        (optional, kalau ada)
  4) 03_store_to_database.py   (optional, kalau enabled)

Config diambil dari:
- .env  (pakai nama variabel: DATASOURCE, PATH_NLP_OUT, PATH_LDA_OUT, ...)
- bisa dioverride via CLI

Logging: auto ke log_YYYY-MM-DD.txt di ml_engine/log/<project>/
"""

from pathlib import Path
import os, sys, argparse, datetime, importlib.util, contextlib

# HERE = direktori ml_engine
HERE = Path(__file__).resolve().parent


# --- load .env ---
def load_env():
    loaded = False
    try:
        from dotenv import load_dotenv
        load_dotenv()
        load_dotenv(str(HERE / ".env"))
        loaded = True
    except Exception:
        loaded = False

    # 2) kalau gak ada python-dotenv, baca manual
    if not loaded:
        env_path = HERE / ".env"
        if env_path.exists():
            with env_path.open("r", encoding="utf-8") as f:
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


# ---------- logging ----------
def log_write(log_fh, msg):
    ts = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"[{ts}] {msg}"
    print(line)
    if log_fh:
        try:
            log_fh.write(line + "\n")
            log_fh.flush()
        except Exception:
            pass


# ---------- utils ----------
def file_nonempty(path) -> bool:
    """Cek file ada & size > 0 (boleh Path atau str)."""
    try:
        p = Path(path)
        return p.is_file() and p.stat().st_size > 0
    except Exception:
        return False


@contextlib.contextmanager
def temp_argv(new_argv):
    old = sys.argv[:]
    sys.argv = new_argv
    try:
        yield
    finally:
        sys.argv = old


def load_module_from(path, name: str):
    path = str(path)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def str2bool(v):
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    return str(v).lower() in ("1", "true", "yes", "on")


# ---------- main ----------
def main():
    nameOfProject = os.getenv("PROJECT_NAME", "idneasyfix")

    parser = argparse.ArgumentParser(description="Run EasyFix pipeline (in-process)")
    parser.add_argument("--input", type=str, default=None, help="Path to Bugzilla JSONL")
    parser.add_argument("--nlp_out", type=str, default=None, help="Output dir for NLP step")
    parser.add_argument("--lda_out", type=str, default=None, help="Output dir for LDA step")
    parser.add_argument("--auto_topics_num", type=str, default=True)
    parser.add_argument("--num_topics", type=int, default=None)
    parser.add_argument("--passes", type=int, default=None)
    parser.add_argument("--auto_k", action="store_true", help="Choose K automatically (overrides env)")
    parser.add_argument("--sim_threshold", type=float, default=None)
    parser.add_argument("--dup_threshold", type=float, default=None)
    parser.add_argument("--force_nlp", action="store_true", help="Force re-run NLP even if bugs_clean.csv exists")

    # neo4j
    parser.add_argument("--neo4j-enable", action="store_true", help="Store LDA relations to Neo4j (03_store_to_database.py)")
    parser.add_argument("--neo4j-uri", type=str, default=None)
    parser.add_argument("--neo4j-user", type=str, default=None)
    parser.add_argument("--neo4j-pass", type=str, default=None)
    parser.add_argument("--neo4j-db", type=str, default=None)

    args = parser.parse_args()

    # ====== ambil dari ENV ======
    # Semua default path dibuat RELATIF ke ml_engine (HERE)
    env_input   = os.getenv("DATASOURCE", f"datasource/{nameOfProject}.jsonl")
    env_nlp_out = os.getenv("PATH_NLP_OUT", f"out_nlp/{nameOfProject}")
    env_lda_out = os.getenv("PATH_LDA_OUT", f"out_lda/{nameOfProject}")

    env_auto_topics_num   = str2bool(os.getenv("AUTO_TOPICS_NUM", "true"))
    env_num_topics   = int(os.getenv("NUM_TOPICS", "10"))
    env_passes       = int(os.getenv("PASSES", "8"))
    env_auto_k       = str2bool(os.getenv("AUTO_K", "false"))
    env_sim_th       = float(os.getenv("SIM_THRESHOLD", "0.6"))
    env_dup_th       = float(os.getenv("DUP_THRESHOLD", "0.8"))

    env_neo4j_enable = str2bool(os.getenv("NEO4J_ENABLE", "true"))
    env_neo4j_uri    = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    env_neo4j_user   = os.getenv("NEO4J_USER", "neo4j")
    env_neo4j_pass   = os.getenv("NEO4J_PASS", "neo4j2025")
    env_neo4j_db     = os.getenv("NEO4J_DB", nameOfProject)

    # log dir default: ml_engine/log/<project>/
    default_log_dir = HERE / "log" / nameOfProject
    env_log_dir_str = os.getenv("LOG_DIR", str(default_log_dir))
    env_log_dir = Path(env_log_dir_str)

    # ====== gabung ENV + CLI  ======
    # Input
    raw_input = args.input or env_input
    input_path = Path(raw_input)
    if not input_path.is_absolute():
        input_path = HERE / input_path  # => ml_engine/datasource/...

    # Output NLP & LDA -> selalu di dalam ml_engine/
    raw_nlp_out = args.nlp_out or env_nlp_out
    raw_lda_out = args.lda_out or env_lda_out

    nlp_out = Path(raw_nlp_out)
    lda_out = Path(raw_lda_out)

    if not nlp_out.is_absolute():
        nlp_out = HERE / nlp_out   # => ml_engine/out_nlp/<project>
    if not lda_out.is_absolute():
        lda_out = HERE / lda_out   # => ml_engine/out_lda/<project>

    auto_topics_num = args.auto_topics_num or env_auto_topics_num
    num_topics = args.num_topics or env_num_topics
    passes_lda = args.passes or env_passes
    sim_th     = args.sim_threshold or env_sim_th
    dup_th     = args.dup_threshold or env_dup_th
    auto_k     = args.auto_k or env_auto_k

    neo4j_enable = args.neo4j_enable or env_neo4j_enable
    neo4j_uri    = args.neo4j_uri or env_neo4j_uri
    neo4j_user   = args.neo4j_user or env_neo4j_user
    neo4j_pass   = args.neo4j_pass or env_neo4j_pass
    neo4j_db     = (args.neo4j_db or env_neo4j_db)

    print(f"num_topics {num_topics}")
    print(f"[DEBUG] input_path = {input_path}")
    print(f"[DEBUG] nlp_out    = {nlp_out}")
    print(f"[DEBUG] lda_out    = {lda_out}")
    print(f"[DEBUG] log_dir    = {env_log_dir}")

    # ====== logging ======
    date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    env_log_dir.mkdir(parents=True, exist_ok=True)
    log_path = env_log_dir / f"log_{date_str}.txt"

    try:
        log_fh = log_path.open("a", encoding="utf-8")
        log_write(log_fh, f"=== Pipeline started (log: {log_path.name}) ===")
    except Exception as e:
        log_fh = None
        print(f"[WARN] Could not open log file {log_path}: {e}")

    # ====== cek file script ======
    nlp_path   = HERE / "01_nlp_preprocess.py"
    lda_path   = HERE / "02_lda_topics.py"
    store_path = HERE / "03_store_to_database.py"
    clean_path = HERE / "03_clean_topics.py"

    if (not nlp_path.exists()) or (not lda_path.exists()):
        log_write(log_fh, "Missing scripts (01_nlp_preprocess.py / 02_lda_topics.py).")
        sys.exit(1)

    # bikin folder dari hasil MERGE ENV+CLI (sudah Path)
    nlp_out.mkdir(parents=True, exist_ok=True)
    lda_out.mkdir(parents=True, exist_ok=True)

    bugs_clean_path = nlp_out / "bugs_clean.csv"

    # --- STEP 1: NLP ---
    if not args.force_nlp and file_nonempty(bugs_clean_path):
        log_write(log_fh, f"[NLP] Skipped: found {bugs_clean_path}")
    else:
        log_write(log_fh, "[NLP] Running 01_nlp_preprocess.py in-process…")
        nlp_mod = load_module_from(nlp_path, "nlp_step")
        if not hasattr(nlp_mod, "main"):
            log_write(log_fh, "[NLP][ERROR] 01_nlp_preprocess.py must define main()")
            sys.exit(1)
        nlp_argv = [str(nlp_path), "--input", str(input_path), "--outdir", str(nlp_out)]
        with temp_argv(nlp_argv):
            nlp_mod.main()
        if not file_nonempty(bugs_clean_path):
            log_write(log_fh, f"[NLP][ERROR] Missing or empty {bugs_clean_path} after NLP.")
            sys.exit(1)

    # --- STEP 2: LDA ---
    lda_models = lda_out / "lda_sklearn_model_meta.npz"
    log_write(log_fh, "[LDA] Running 02_lda_topics.py in-process…")
    run_lda = True
    if file_nonempty(lda_models):
        # kalau mau beneran skip, set False
        log_write(log_fh, f"[LDA] Skipped: found {lda_models}")
        run_lda = False

    if run_lda:
        lda_mod = load_module_from(lda_path, "lda_step")
        if not hasattr(lda_mod, "main"):
            log_write(log_fh, "[LDA][ERROR] 02_lda_topics.py must define main()")
            sys.exit(1)

        lda_argv = [
            str(lda_path),
            "--input", str(bugs_clean_path),
            "--outdir", str(lda_out),
            "--auto_topics_num", str(auto_topics_num),
            "--num_topics", str(num_topics),
            "--passes", str(passes_lda),
            "--sim_threshold", str(sim_th),
            "--dup_threshold", str(dup_th),
            "--log_path", str(log_path),
        ]
        if auto_k:
            lda_argv.append("--auto_k")

        with temp_argv(lda_argv):
            lda_mod.main()

    # --- STEP 3: Topic Cleaning (optional) ---
    log_write(log_fh, "[CLEAN] Running 03_clean_topics.py in-process…")
    if clean_path.exists():
        clean_mod = load_module_from(clean_path, "clean_step")
        if hasattr(clean_mod, "main"):
            sys.argv = [
                "03_clean_topics.py",
                "--project", nameOfProject,
                "--topics", str(lda_out / "topics.csv"),
                "--bugs", str(lda_out / "bugs_with_topics.csv"),
                "--outdir", str(lda_out),
            ]
            try:
                clean_mod.main()
            except Exception as e:
                log_write(log_fh, f"[CLEAN][ERROR] {e}")
        else:
            log_write(log_fh, "[CLEAN][ERROR] 03_clean_topics.py has no main()")
    else:
        log_write(log_fh, "[CLEAN][WARN] 03_clean_topics.py not found — skipping")

    # --- STEP 4: Store to Neo4j ---
    if neo4j_enable:
        if not store_path.exists():
            log_write(log_fh, "[NEO4J][ERROR] 03_store_to_database.py not found, skip.")
        else:
            log_write(log_fh, "[NEO4J] Running 03_store_to_database.py in-process…")
            store_mod = load_module_from(store_path, "store_step")
            if not hasattr(store_mod, "main"):
                log_write(log_fh, "[NEO4J][ERROR] 03_store_to_database.py must define main()")
            else:
                store_argv = [
                    str(store_path),
                    "--in_lda", str(lda_out),
                    "--neo4j-uri", neo4j_uri,
                    "--neo4j-user", neo4j_user,
                    "--neo4j-pass", neo4j_pass,
                    "--neo4j-db", neo4j_db,
                    "--log_path", str(log_path),
                ]
                with temp_argv(store_argv):
                    store_mod.main()

    # baru kita tutup log
    log_write(log_fh, "=== Pipeline finished successfully ===")
    if log_fh:
        try:
            log_fh.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
