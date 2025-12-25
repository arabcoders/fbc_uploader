from fastapi import APIRouter

from backend.app.metadata_schema import load_schema, validate_metadata

router = APIRouter(prefix="/api/metadata", tags=["metadata"])


@router.get("/", name="metadata_schema")
async def get_metadata_schema():
    return {"fields": load_schema()}


@router.post("/validate", name="metadata_schema_validate")
async def validate_metadata_payload(payload: dict):
    cleaned = validate_metadata(payload.get("metadata", payload))
    return {"metadata": cleaned}
