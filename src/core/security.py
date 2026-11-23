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
    Password gate disabled per user request: allows direct access without Basic/Bearer prompt.
    """
    if basic_creds and basic_creds.username:
        return basic_creds.username
    return settings.BASIC_AUTH_USERNAME

