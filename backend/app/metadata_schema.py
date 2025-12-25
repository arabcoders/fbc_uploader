import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status

from .config import settings

_cache: dict[str, Any] = {"mtime": None, "schema": []}


def load_schema() -> list[dict]:
    path = Path(settings.config_path).expanduser() / "metadata.json"
    if not path.exists():
        return []

    mtime = path.stat().st_mtime
    if _cache["mtime"] == mtime:
        return _cache["schema"]

    data = json.loads(path.read_text())
    if not isinstance(data, list):
        raise HTTPException(status_code=500, detail="metadata.json must be a list")

    _cache["mtime"] = mtime
    _cache["schema"] = data
    return data


def _error(field: str, msg: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail={"field": field, "message": msg},
    )


def _coerce_type(value: Any, ftype: str, field: str):
    if value is None:
        return None
    try:
        if ftype in ("string", "text"):
            return str(value)
        if ftype == "boolean":
            if isinstance(value, bool):
                return value
            if str(value).lower() in ("true", "1", "yes", "on"):
                return True
            if str(value).lower() in ("false", "0", "no", "off"):
                return False
            raise ValueError
        if ftype == "number":
            return float(value)
        if ftype == "integer":
            return int(value)
        if ftype == "date":
            return date.fromisoformat(str(value))
        if ftype == "datetime":
            return datetime.fromisoformat(str(value))
        if ftype in ("select", "multiselect"):
            return value
    except Exception:
        raise _error(field, f"Invalid {ftype} value")
    return value


def validate_metadata(values: dict[str, Any]) -> dict[str, Any]:
    schema = load_schema()
    cleaned: dict[str, Any] = {}
    for field in schema:
        key = field["key"]
        ftype = field.get("type", "string")
        required = field.get("required", False)
        val = values.get(key)
        if val is None:
            if required:
                raise _error(key, "Field is required")
            continue
        val = _coerce_type(val, ftype, key)
        allow_custom = field.get("allowCustom") or field.get("allow_custom")
        if ftype == "multiselect":
            if not isinstance(val, list):
                raise _error(key, "Must be a list")
            allowed = field.get("options")
            if allowed and not allow_custom:
                allowed_vals = [a if isinstance(a, str) else a.get("value") for a in allowed]
                for v in val:
                    if v not in allowed_vals:
                        raise _error(key, f"Invalid option: {v}")
        if ftype == "select":
            allowed = field.get("options")
            if allowed and not allow_custom:
                allowed_vals = [a if isinstance(a, str) else a.get("value") for a in allowed]
                if val not in allowed_vals:
                    raise _error(key, "Invalid option")
        if ftype in ("string", "text"):
            min_len = field.get("minLength")
            max_len = field.get("maxLength")
            if min_len and len(val) < min_len:
                raise _error(key, f"Must be at least {min_len} characters")
            if max_len and len(val) > max_len:
                raise _error(key, f"Must be at most {max_len} characters")
            regex = field.get("regex")
            if regex:
                import re

                if not re.fullmatch(regex, val):
                    raise _error(key, "Invalid format")
        if ftype in ("number", "integer"):
            min_v = field.get("min")
            max_v = field.get("max")
            if min_v is not None and val < min_v:
                raise _error(key, f"Must be >= {min_v}")
            if max_v is not None and val > max_v:
                raise _error(key, f"Must be <= {max_v}")
        if isinstance(val, (datetime, date)):
            cleaned[key] = val.isoformat()
        else:
            cleaned[key] = val
    return cleaned
