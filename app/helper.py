
import re

def _dbname(org: str, proj: str) -> str:
    """
    Generate Neo4j database name from organization + project.
    MUST be konsisten dengan database_name di Firestore (project_service).
    Example: "EasyFix Labs" + "Alpha Project" -> "easyfix_labs_alpha_project"
    """
    def to_db(x: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", x.strip().lower()).strip("_")
    base = f"{to_db(org)}{to_db(proj)}"
    return base[:63] if len(base) > 63 else base

def normalize_topic_id(tid):
    # paksa jadi string
    if tid is None:
        return None
    try:
        return str(int(tid))    # kalau "4", 4, "004" -> "4"
    except:
        return str(tid).strip()
