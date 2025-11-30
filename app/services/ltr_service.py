from typing import List, Dict, Any, Tuple
from app.core.neo4j_conn import get_driver


FEATURE_COLUMNS = [
    "topic_match",
    "component_match",
    "bugs_fixed_total",
    "bugs_fixed_topic",
    "recent_days",
    # tambahkan fitur lain yang kamu gunakan di training
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
        "name": dev_ctx.get("name"),
        "bugs_fixed_total": dev_bugs_total,
        "bugs_fixed_topic": dev_bugs_topic,
        "recent_days": recent_days,
    }

    return features, meta
