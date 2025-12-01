from typing import List, Dict, Any, Tuple
import pandas as pd
import numpy as np
import datetime
from app.core.neo4j_conn import get_driver

FEATURE_COLUMNS = [
    "topic_match",
    "component_match",
    "bugs_fixed_total",
    "bugs_fixed_topic",
    "recent_days",
]

async def fetch_bug_context(database: str, bug_id: str) -> Dict[str, Any]:
    """
    Ambil informasi penting dari bug, misal:
    - topic_id
    - component
    - severity
    - dll
    """
    driver = await get_driver()
    cypher = """
    MATCH (b:Bug {bug_id: $bug_id})
    RETURN
      b.bug_id AS bug_id,
      b.topic_id AS topic_id,
      b.component AS component,
      b.severity AS severity,
      b.summary AS summary
    """
    async with driver.session(database=database) as session:
        result = await session.run(cypher, bug_id=bug_id)
        record = await result.single()
        if not record:
            return {}
        return dict(record)


async def fetch_candidate_developers(database: str, bug_topic_id: int):
    driver = await get_driver()
    cypher = """
    MATCH (d:Developer)<-[:ASSIGNED_TO]-(bTopic:Bug)
    WHERE toString(bTopic.topic_id) = toString($topic_id)
    WITH d, count(bTopic) AS bugs_fixed_topic

    MATCH (d)<-[:ASSIGNED_TO]-(bAll:Bug)
    WITH d,
         bugs_fixed_topic,
         count(bAll) AS bugs_fixed_total,
         collect(DISTINCT bAll.component) AS dev_components

    RETURN
      d.dev_id              AS developer_id,
      bugs_fixed_total,
      bugs_fixed_topic,
      dev_components
    """

    async with driver.session(database=database) as session:
        result = await session.run(cypher, topic_id=bug_topic_id)
        rows = [record async for record in result]

    # ubah ke list[dict]
    candidates = []
    for r in rows:
        candidates.append({
            "developer_id": r["developer_id"],
            "bugs_fixed_total": r["bugs_fixed_total"],
            "bugs_fixed_topic": r["bugs_fixed_topic"],
            "components": r["dev_components"]
        })
    return candidates


def compute_days_since_last_active(last_active_at) -> float:
    """
    Hitung jumlah hari sejak developer terakhir aktif.
    last_active_at diharapkan string ISO timestamp atau date.
    Di sini pseudo, kamu sesuaikan dengan format datamu.
    """
    import datetime

    if not last_active_at:
        return 9999.0

    try:
        dt = datetime.datetime.fromisoformat(last_active_at)
    except Exception:
        return 9999.0

    today = datetime.datetime.utcnow()
    delta = today - dt
    return float(delta.days)


def compute_component_match(bug_component, dev_components) -> float:
    """
    Hitung skor kecocokan komponen, misal 0 atau 1.
    Kalau komponen dev berupa list/string, sesuaikan.
    """
    if not bug_component or not dev_components:
        return 0.0

    if isinstance(dev_components, str):
        # misal disimpan sebagai "UI,Auth,Network"
        dev_components_set = {c.strip() for c in dev_components.split(",")}
    else:
        dev_components_set = set(dev_components)

    return 1.0 if bug_component in dev_components_set else 0.0


def build_feature_row(
    bug_ctx: Dict[str, Any],
    dev_ctx: Dict[str, Any],
) -> Tuple[Dict[str, float], Dict[str, Any]]:
    """
    Bangun satu baris fitur untuk pair (bug, dev).
    Return:
      - dict fitur numerik
      - dict meta (developer_id, name etc.) untuk dikembalikan ke API
    """
    bug_topic = bug_ctx.get("topic_id")
    dev_bugs_total = dev_ctx.get("bugs_fixed_total") or 1
    dev_bugs_topic = dev_ctx.get("bugs_fixed_topic") or 0

    topic_match = float(dev_bugs_topic) / float(dev_bugs_total)
    component_match = compute_component_match(
        bug_ctx.get("component"),
        dev_ctx.get("components"),
    )
    recent_days = compute_days_since_last_active(dev_ctx.get("last_active_at"))

    features = {
        "topic_match": topic_match,
        "component_match": component_match,
        "bugs_fixed_total": float(dev_bugs_total),
        "bugs_fixed_topic": float(dev_bugs_topic),
        "recent_days": float(recent_days),
        # TODO: tambahkan fitur lain yang kamu pakai di training
    }

    meta = {
        "developer_id": dev_ctx["developer_id"],
        "bugs_fixed_total": dev_bugs_total,
        "bugs_fixed_topic": dev_bugs_topic,
        "recent_days": recent_days,
    }

    return features, meta

def compute_days_since_last_active(last_active_at):
    if not last_active_at:
        return 9999
    try:
        dt = datetime.datetime.fromisoformat(last_active_at)
        return (datetime.datetime.utcnow() - dt).days
    except:
        return 9999


def component_match(bug_comp, dev_comp):
    if not bug_comp or not dev_comp:
        return 0
    if isinstance(dev_comp, str):
        d = {x.strip() for x in dev_comp.split(",")}
    else:
        d = set(dev_comp)
    return 1 if bug_comp in d else 0


def build_training_dataset(
    bug_dev_fixes: List[Dict[str, Any]],
    all_devs: List[Dict[str, Any]],
    negatives_per_bug: int = 10,
) -> pd.DataFrame:
    """
    Build dataset untuk Learning-to-Rank dari:
      - bug_dev_fixes: pasangan (bug, developer) yang sudah FIXED/RESOLVED
                       hasil dari fetch_bug_dev_pairs(), misal kolom:
                         bug_id, developer_id, topic_id, component, summary
      - all_devs: daftar semua developer (hasil fetch_all_developers), minimal punya:
                         developer_id

    Output: DataFrame dengan kolom:
      bug_id, developer_id, topic_id, component, label,
      bugs_fixed_total, bugs_fixed_topic,
      topic_match, component_match, recent_days (dummy)
    """

    if not bug_dev_fixes:
        return pd.DataFrame()

    df_fix = pd.DataFrame(bug_dev_fixes)

    # Normalisasi nama kolom (jaga-jaga)
    if "developer_id" not in df_fix.columns and "dev_id" in df_fix.columns:
        df_fix = df_fix.rename(columns={"dev_id": "developer_id"})

    required_cols = {"bug_id", "developer_id", "topic_id", "component"}
    missing = required_cols - set(df_fix.columns)
    if missing:
        raise ValueError(f"[build_training_dataset] Missing columns in bug_dev_fixes: {missing}")

    # --- Aggregations di level developer ---

    # 1) Total bug FIXED yang pernah dikerjakan setiap dev (semua topic)
    #    → ukuran pengalaman global
    dev_total = (
        df_fix.groupby("developer_id")["bug_id"]
        .nunique()  # atau .size() kalau satu dev-bug bisa muncul lebih dari sekali
        .to_dict()
    )

    # 2) Jumlah bug per (developer, topic_id)
    #    → ukuran keahlian spesifik per topik
    dev_topic_counts = (
        df_fix.groupby(["developer_id", "topic_id"])["bug_id"]
        .nunique()
        .to_dict()
    )

    # 3) Riwayat komponen per developer (list of components yang pernah dia handle)
    dev_components = (
        df_fix.groupby("developer_id")["component"]
        .apply(lambda s: sorted({c for c in s.dropna()}))
        .to_dict()
    )

    # --- Siapkan daftar semua dev untuk negative sampling ---

    all_devs_df = pd.DataFrame(all_devs)
    if "developer_id" not in all_devs_df.columns and "dev_id" in all_devs_df.columns:
        all_devs_df = all_devs_df.rename(columns={"dev_id": "developer_id"})

    if "developer_id" not in all_devs_df.columns:
        raise ValueError("[build_training_dataset] all_devs must contain 'developer_id' column")

    all_devs_df = all_devs_df.drop_duplicates(subset=["developer_id"]).reset_index(drop=True)

    rows = []

    # --- Loop per bug: buat positive & negative pairs ---

    for bug_id, group in df_fix.groupby("bug_id"):
        topic = group.iloc[0]["topic_id"]
        comp = group.iloc[0]["component"]

        # Developer yang benar-benar FIX bug ini (positives)
        fixed_devs = set(group["developer_id"])

        # Positive pairs: label = 1
        for dev_id in fixed_devs:
            bugs_fixed_total = dev_total.get(dev_id, 0)
            bugs_fixed_topic = dev_topic_counts.get((dev_id, topic), 0)

            if bugs_fixed_total > 0:
                topic_match = float(bugs_fixed_topic) / float(bugs_fixed_total)
            else:
                topic_match = 0.0

            dev_comps = dev_components.get(dev_id, [])
            component_match = 1.0 if comp in dev_comps else 0.0

            # Kalau belum punya timestamp, set dulu dummy (nanti bisa diganti)
            recent_days = 999.0

            rows.append({
                "bug_id": bug_id,
                "developer_id": dev_id,
                "topic_id": topic,
                "component": comp,
                "label": 1,

                "bugs_fixed_total": float(bugs_fixed_total),
                "bugs_fixed_topic": float(bugs_fixed_topic),
                "topic_match": float(topic_match),
                "component_match": float(component_match),
                "recent_days": float(recent_days),
            })

        # Negative sampling: beberapa dev lain yang tidak fix bug ini
        neg_candidates = all_devs_df[~all_devs_df["developer_id"].isin(fixed_devs)]
        if len(neg_candidates) == 0:
            continue

        neg_sample = neg_candidates.sample(
            n=min(negatives_per_bug, len(neg_candidates)),
            replace=False,
            random_state=42,
        )

        for _, dev_row in neg_sample.iterrows():
            dev_id = dev_row["developer_id"]

            bugs_fixed_total = dev_total.get(dev_id, 0)
            bugs_fixed_topic = dev_topic_counts.get((dev_id, topic), 0)

            if bugs_fixed_total > 0:
                topic_match = float(bugs_fixed_topic) / float(bugs_fixed_total)
            else:
                topic_match = 0.0

            dev_comps = dev_components.get(dev_id, [])
            component_match = 1.0 if comp in dev_comps else 0.0

            recent_days = 999.0  # placeholder kalau belum ada tanggal

            rows.append({
                "bug_id": bug_id,
                "developer_id": dev_id,
                "topic_id": topic,
                "component": comp,
                "label": 0,

                "bugs_fixed_total": float(bugs_fixed_total),
                "bugs_fixed_topic": float(bugs_fixed_topic),
                "topic_match": float(topic_match),
                "component_match": float(component_match),
                "recent_days": float(recent_days),
            })

    df_train = pd.DataFrame(rows)

    # Optional: cast jenis data
    if not df_train.empty:
        df_train["label"] = df_train["label"].astype(int)

    return df_train
