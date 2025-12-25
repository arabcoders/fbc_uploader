from typing import Annotated

from fastapi import Header, HTTPException, Query, status

from .config import settings


def verify_admin(
    authorization: Annotated[str | None, Header()] = None,
    api_key: Annotated[str | None, Query(description="API key")] = None,
) -> bool:
    key = None

    if api_key is not None:
        key: str = api_key

    if authorization and authorization.lower().startswith("bearer "):
        key: str = authorization.split(" ", 1)[1]

    if key != settings.admin_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return True
