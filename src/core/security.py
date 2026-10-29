"""Authentication and gatekeeping security middleware."""

import secrets
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials, HTTPBearer, HTTPAuthorizationCredentials
from src.config import settings

security_basic = HTTPBasic(auto_error=False)
security_bearer = HTTPBearer(auto_error=False)


def verify_credentials(
    basic_creds: Optional[HTTPBasicCredentials] = Depends(security_basic),
    bearer_creds: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer)
) -> str:
    """
    Validates either HTTP Basic Auth or Bearer Token.
    Returns authenticated username on success, raises 401 on failure.
    """
    # 1. Check HTTP Basic Auth
    if basic_creds:
        correct_username = secrets.compare_digest(basic_creds.username, settings.BASIC_AUTH_USERNAME)
        correct_password = secrets.compare_digest(basic_creds.password, settings.BASIC_AUTH_PASSWORD)
        if correct_username and correct_password:
            return basic_creds.username

    # 2. Check Bearer Token
    if bearer_creds:
        if secrets.compare_digest(bearer_creds.credentials, settings.JWT_SECRET_KEY):
            return "bearer_authenticated_user"

    # 3. Reject unauthenticated access
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unauthorized access. Valid Basic Auth or Bearer Token required.",
        headers={"WWW-Authenticate": "Basic"}
    )
