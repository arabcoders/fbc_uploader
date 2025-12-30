from typing import Annotated

from fastapi import Header, HTTPException, Query, status

from .config import settings


def optional_admin_check(
    authorization: Annotated[str | None, Header()] = None,
    api_key: Annotated[str | None, Query(description="API key")] = None,
) -> bool:
    """
    Check admin authentication only if public downloads are disabled.

    Args:
        authorization (str | None): The Authorization header.
        api_key (str | None): The API key query parameter.

    Returns:
        bool: True if admin is verified or public downloads are allowed.

    Raises:
        HTTPException: If admin verification fails when required.

    """
    return True if settings.allow_public_downloads else verify_admin(authorization, api_key)


def verify_admin(
    authorization: Annotated[str | None, Header()] = None,
    api_key: Annotated[str | None, Query(description="API key")] = None,
) -> bool:
    """
    Verify the provided admin API key.

    Args:
        authorization (str | None): The Authorization header.
        api_key (str | None): The API key query parameter.

    Returns:
        bool: True if the API key is valid.

    Raises:
        HTTPException: If the API key is invalid or missing.

    """
    key = None

    if api_key is not None:
        key: str = api_key

    if authorization and authorization.lower().startswith("bearer "):
        key: str = authorization.split(" ", 1)[1]

    if key:
        key = key.strip()

    if key != settings.admin_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return True
