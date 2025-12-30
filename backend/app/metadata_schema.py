import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status

from .config import settings

_cache: dict[str, Any] = {"mtime": None, "schema": []}


def load_schema() -> list[dict]:
    """
    Load metadata schema from configuration file.

    Returns:
        list[dict]: List of metadata field definitions

    """
    path = Path(settings.config_path).expanduser() / "metadata.json"
    if not path.exists():
        return []

    mtime: float = path.stat().st_mtime
    if _cache["mtime"] == mtime:
        return _cache["schema"]

    data = json.loads(path.read_text())
    if not isinstance(data, list):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="metadata.json must be a list")

    _cache["mtime"] = mtime
    _cache["schema"] = data
    return data


def _error(field: str, msg: str) -> HTTPException:
    """
    Create a standardized HTTPException for metadata validation errors.

    Args:
        field (str): The metadata field that caused the error.
        msg (str): The error message.

    Returns:
        HTTPException: The constructed exception with status 422.

    """
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail={"field": field, "message": msg},
    )


def _coerce_type(value: Any, ftype: str, field: str) -> Any:
    """
    Coerce a value to the specified metadata field type.

    Args:
        value (Any): The value to coerce.
        ftype (str): The target field type.
        field (str): The metadata field name (for error reporting).

    Returns:
        Any: The coerced value.

    """
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
    """
    Validate and clean metadata values against the schema.

    Args:
        values (dict[str, Any]): The metadata values to validate.

    Returns:
        dict[str, Any]: The cleaned metadata values.

    """
    schema: list[dict] = load_schema()

    cleaned: dict[str, Any] = {}

    for field in schema:
        key: str = field["key"]
        ftype: str = field.get("type", "string")
        required: bool = field.get("required", False)
        val: Any = values.get(key)

        if val is None:
            if required:
                raise _error(key, "Field is required")

            continue

        val = _coerce_type(val, ftype, key)
        allow_custom: bool = field.get("allowCustom") or field.get("allow_custom")

        if "multiselect" == ftype:
            if not isinstance(val, list):
                raise _error(key, "Must be a list")

            allowed: list | None = field.get("options")
            if allowed and not allow_custom:
                allowed_vals: list[str] = [a if isinstance(a, str) else a.get("value") for a in allowed]
                for v in val:
                    if v not in allowed_vals:
                        raise _error(key, f"Invalid option: {v}")

        if "select" == ftype:
            allowed: list | None = field.get("options")
            if allowed and not allow_custom:
                allowed_vals: list[str] = [a if isinstance(a, str) else a.get("value") for a in allowed]
                if val not in allowed_vals:
                    raise _error(key, "Invalid option")

        if ftype in ("string", "text"):
            if (min_len := field.get("minLength")) and len(val) < min_len:
                raise _error(key, f"Must be at least {min_len} characters")

            if (max_len := field.get("maxLength")) and len(val) > max_len:
                raise _error(key, f"Must be at most {max_len} characters")

            if regex := field.get("regex"):
                import re

                if not re.fullmatch(regex, val):
                    raise _error(key, "Invalid format")

        if ftype in ("number", "integer"):
            min_v: int | None = field.get("min")
            max_v: int | None = field.get("max")

            if min_v is not None and val < min_v:
                raise _error(key, f"Must be >= {min_v}")

            if max_v is not None and val > max_v:
                raise _error(key, f"Must be <= {max_v}")

        cleaned[key] = val.isoformat() if isinstance(val, (datetime, date)) else val

    return cleaned
