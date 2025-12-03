
import re
from fastapi import HTTPException
import json

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
    
# Required fields based on your sample JSONL file
REQUIRED_KEYS = {
    "id",
    "summary",
    "status",
    "resolution",
    "product",
    "component",
    "creation_time",
    "last_change_time",
    "creator",
    "assigned_to",
    "keywords",
    "url",
    "depends_on",
    "dupe_of",
    "commit_messages",
    "commit_refs",
    "files_changed",
}


def validate_datacollection_jsonl(raw: bytes):
    """
    Validate datacollection JSONL:
    - valid JSON per line
    - must have required fields
    - basic type validation
    """
    try:
        text = raw.decode("utf-8")
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="File must be UTF-8 encoded"
        )

    lines = [ln for ln in text.splitlines() if ln.strip()]

    if not lines:
        raise HTTPException(
            status_code=400,
            detail="Uploaded file is empty"
        )

    max_check = min(len(lines), 500)

    for idx in range(max_check):
        line = lines[idx]

        # --- JSON validation ---
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Line {idx+1} is not valid JSON: {e}"
            )

        if not isinstance(obj, dict):
            raise HTTPException(
                status_code=400,
                detail=f"Line {idx+1} is not a JSON object"
            )

        # --- Key validation ---
        keys = set(obj.keys())
        missing = REQUIRED_KEYS - keys

        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"Line {idx+1} missing required keys: {sorted(missing)}"
            )

        # --- Type validation ---
        if not isinstance(obj["id"], int):
            raise HTTPException(
                status_code=400,
                detail=f"Line {idx+1}: 'id' must be int"
            )

        if not isinstance(obj["summary"], str):
            raise HTTPException(
                status_code=400,
                detail=f"Line {idx+1}: 'summary' must be string"
            )

        list_fields = [
            "keywords",
            "depends_on",
            "commit_messages",
            "commit_refs",
            "files_changed"
        ]
        for f in list_fields:
            if not isinstance(obj[f], list):
                raise HTTPException(
                    status_code=400,
                    detail=f"Line {idx+1}: '{f}' must be list"
                )

        # dupe_of: int or null
        if obj["dupe_of"] is not None and not isinstance(obj["dupe_of"], int):
            raise HTTPException(
                status_code=400,
                detail=f"Line {idx+1}: 'dupe_of' must be int or null"
            )

    # PASSED
    return True
