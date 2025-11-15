# app/services/ml_runner.py
import os
import subprocess
from pathlib import Path
from typing import Dict, Optional

from app.core.firebase import db
from app.config import settings
from neo4j import GraphDatabase
from firebase_admin import firestore
from datetime import datetime

# ML Engine paths from config
ML_ENGINE_DIR = Path(settings.ML_ENGINE_DIR)  
ML_PYTHON_BIN = settings.ML_PYTHON_BIN
ML_MAIN_SCRIPT = settings.ML_MAIN_SCRIPT

# Datasource base folder (adjust if needed)
ML_DATASOURCE_BASE = ML_ENGINE_DIR / "datasource"


def _project_doc(org_slug: str, project_slug: str):
    return (
        db.collection("organizations")
        .document(org_slug)
        .collection("projects")
        .document(project_slug)
    )


def _clear_ml_status(org_slug: str, project_slug: str):
    doc_ref = _project_doc(org_slug, project_slug)
    doc_ref.update({
        "ml_status.import": "pending",
        "ml_status.training": "pending",
        "ml_status.stage": "STARTING",
        "ml_status.progress": 0,
        "ml_status.message": "Pipeline starting...",
        "ml_status.log_text": "",  
    })
    
def _append_ml_log_text(org_slug: str, project_slug: str, msg: str):
    doc_ref = _project_doc(org_slug, project_slug)

    # 1) Ambil value sebelumnya
    snap = doc_ref.get()
    data = snap.to_dict() or {}
    ml_status = data.get("ml_status") or {}
    prev_text = ml_status.get("log_text") or ""

    # 2) Buat baris baru dengan timestamp
    ts = datetime.utcnow().isoformat() + "Z"
    line = f"{ts} {msg}\n"

    # 3) Concat & update
    new_text = prev_text + line

    doc_ref.update({
        "ml_status.log_text": new_text,
        "ml_status.updated_at": firestore.SERVER_TIMESTAMP,
    })
    
def _update_ml_status(org_slug: str, project_slug: str, status: Dict):
    """
    Update field-field ml_status.* TANPA menghapus log_text.
    """
    doc_ref = _project_doc(org_slug, project_slug)
    update_data = {}

    for k, v in status.items():
        update_data[f"ml_status.{k}"] = v

    update_data["ml_status.updated_at"] = firestore.SERVER_TIMESTAMP

    doc_ref.update(update_data)


def check_ml_environment(database_name: str) -> Dict:
    """
    Cek environment sebelum menjalankan ML engine:
    - Folder ML engine
    - File datasource <database_name>.jsonl
    - Koneksi Neo4j & database dgn nama <database_name>
    """
    result = {
        "ok": True,
        "ml_engine_dir_ok": True,
        "datasource_ok": True,
        "neo4j_ok": True,
        "datasource_path": None,
        "neo4j_error": None,
    }

    # 1) cek folder ML engine
    if not ML_ENGINE_DIR.is_dir():
        result["ok"] = False
        result["ml_engine_dir_ok"] = False
        return result

    # 2) cek file datasource
    datasource_path = (ML_DATASOURCE_BASE / f"{database_name}.jsonl").resolve()
    datasource_path = datasource_path.resolve()
    result["datasource_path"] = str(datasource_path)

    if not datasource_path.exists():
        result["ok"] = False
        result["datasource_ok"] = False
        # lanjut cek Neo4j juga, biar user dapat info lengkap

    # 3) cek Neo4j (URI & auth dari settings, nama DB = database_name dari Firestore)
    try:
        driver = GraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
        )
        with driver:
            with driver.session(database=database_name) as session:
                session.run("RETURN 1 AS ok").single()
    except Exception as e:
        result["ok"] = False
        result["neo4j_ok"] = False
        result["neo4j_error"] = f"{e.__class__.__name__}: {e}"

    return result


def _run_pipeline_for_project(
    org_slug: str,
    project_slug: str,
    database_name: str,
    extra_env: Optional[Dict[str, str]] = None,
):
    extra_env = extra_env or {}
    _clear_ml_status(org_slug, project_slug)

    _update_ml_status(org_slug, project_slug, {
        "import": "in_progress",
        "training": "in_progress",
        "stage": "STARTING",
        "progress": 1,
        "message": "Starting ML pipeline",
    })

    # Validate ML engine folder
    if not ML_ENGINE_DIR.is_dir():
        _update_ml_status(org_slug, project_slug, {
            "import": "failed",
            "training": "failed",
            "stage": "FAILED",
            "message": f"ML_ENGINE_DIR not found: {ML_ENGINE_DIR}"
        })
        return

    # datasource file = datasource/<database_name>.jsonl
    datasource_path = (ML_DATASOURCE_BASE / f"{database_name}.jsonl").resolve()


    if not datasource_path.exists():
        _update_ml_status(org_slug, project_slug, {
            "import": "failed",
            "training": "failed",
            "stage": "FAILED",
            "message": f"Datasource not found: {datasource_path}"
        })
        return

    # ENV untuk ML engine main.py
    env = os.environ.copy()
    env["DATASOURCE"] = str(datasource_path)
    env["PATH_NLP_OUT"] = str(ML_ENGINE_DIR / "out_nlp" / database_name)
    env["PATH_LDA_OUT"] = str(ML_ENGINE_DIR / "out_lda" / database_name)
    env["NEO4J_ENABLE"] = "true"

    # Neo4j config dari settings, NAMA DATABASE dari Firestore (concat org+project, tanpa underscore)
    env["NEO4J_URI"] = settings.NEO4J_URI
    env["NEO4J_USER"] = settings.NEO4J_USER
    env["NEO4J_PASS"] = settings.NEO4J_PASSWORD
    env["NEO4J_DB"] = database_name   

    # Inject override tambahan (kalau ada)
    for k, v in extra_env.items():
        env[str(k).upper()] = str(v)

    cmd = [
        ML_PYTHON_BIN,
        ML_MAIN_SCRIPT,
        "--input", str(datasource_path),
        "--nlp_out", str((ML_ENGINE_DIR / "out_nlp" / database_name).resolve()),
        "--lda_out", str((ML_ENGINE_DIR / "out_lda" / database_name).resolve()),
        "--neo4j-enable",
        "--neo4j-uri", settings.NEO4J_URI,
        "--neo4j-user", settings.NEO4J_USER,
        "--neo4j-pass", settings.NEO4J_PASSWORD,
        "--neo4j-db", database_name   
    ]

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(ML_ENGINE_DIR),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        for line in proc.stdout:
            msg = line.strip()
            if not msg:
                continue

           
            # append log text
            try:
                _append_ml_log_text(org_slug, project_slug, msg[:1000])
            except Exception:
                pass   # jangan hentikan pipeline


            # 2) update ringkasan status
            lower = msg.lower()
            stage = "RUNNING"
            progress = 5

            if "[nlp]" in lower:
                stage, progress = "NLP_PREPROCESS", 25
            elif "[lda]" in lower:
                stage, progress = "LDA_TRAIN", 60
            elif "[clean]" in lower:
                stage, progress = "TOPIC_CLEAN", 75
            elif "[neo4j]" in lower:
                stage, progress = "GRAPH_WRITE", 90

            _update_ml_status(org_slug, project_slug, {
                "import": "in_progress",
                "training": "in_progress",
                "stage": stage,
                "progress": progress,
                "message": msg[:500],
            })


        rc = proc.wait()

        if rc != 0:
            _append_ml_log_text(org_slug, project_slug, f"[ERROR] ML engine exited with code {rc}")
            _update_ml_status(org_slug, project_slug, {
                "import": "failed",
                "training": "failed",
                "stage": "FAILED",
                "message": f"ML engine exited with code {rc}",
                "progress": 100,  
            })
        else:
            _append_ml_log_text(org_slug, project_slug, "[INFO] Pipeline completed successfully")
            _update_ml_status(org_slug, project_slug, {
                "import": "done",
                "training": "done",
                "stage": "COMPLETED",
                "message": "ML pipeline completed successfully",
                "progress": 100,
            })


    except Exception as e:
        _update_ml_status(org_slug, project_slug, {
            "import": "failed",
            "training": "failed",
            "stage": "FAILED",
            "progress"  : 100,
            "message": f"Exception: {e}",
        })


def schedule_pipeline_for_project(
    bg,
    org_slug: str,
    project_slug: str,
    database_name: str,
    extra_env: Optional[Dict[str, str]] = None,
):
    bg.add_task(_run_pipeline_for_project, org_slug, project_slug, database_name, extra_env or {})
