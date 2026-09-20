"""Value canonicalization for scoring (later: DB loading).
Small and explicit on purpose — the model transcribes, we canonicalize."""
import re
from datetime import datetime

DATE_FORMATS = ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y", "%Y-%m-%d")

# identity fields: case-insensitive by design (v1: employee_id, v2: roll_number)
ID_FIELDS = {"employee_id", "roll_number"}


def normalize_value(value, data_type: str, field_name: str = ""):
    if value is None:
        return None
    v = " ".join(str(value).split())
    if v == "":
        return None
    if v == "?":                       # unreadable GT marker — kept as-is
        return "?"
    if field_name in ID_FIELDS:
        return v.upper()
    if data_type == "date":
        for fmt in DATE_FORMATS:
            try:
                return datetime.strptime(v, fmt).date().isoformat()
            except ValueError:
                continue
        return v
    if data_type == "integer":
        m = re.search(r"-?\d+", v)
        return m.group(0) if m else v
    if data_type == "float":
        m = re.search(r"-?\d+(?:\.\d+)?", v)
        return m.group(0) if m else v
    if data_type == "boolean":
        low = v.lower()
        if low in ("yes", "true", "y", "yrs"):
            return "true"
        if low in ("no", "false", "n", "nil", "none"):
            return "false"
        return v
    return v
