from typing import Any

from fastapi import APIRouter

from backend.app.metadata_schema import load_schema, validate_metadata

router = APIRouter(prefix="/api/metadata", tags=["metadata"])


@router.get("/", name="metadata_schema")
async def get_metadata_schema() -> dict[str, list[dict]]:
    """
    Retrieve the metadata schema fields.

    Returns:
        dict: A dictionary containing the metadata schema fields.

    """
    return {"fields": load_schema()}


@router.post("/validate", name="metadata_schema_validate")
async def validate_metadata_payload(payload: dict) -> dict[str, dict[str, Any]]:
    """
    Validate and clean the provided metadata payload.

    Args:
        payload: Metadata payload to validate

    Returns:
        dict: A dictionary containing the cleaned metadata

    """
    return {"metadata": validate_metadata(payload.get("metadata", payload))}
