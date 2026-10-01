"""Bearer-token authentication."""

import hmac
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import SecretStr

from jouskaio_api.core.errors import AuthenticationError

bearer_scheme = HTTPBearer(
    auto_error=False,
    description="The value of `JOUSKAIO_API_TOKEN`, sent as `Authorization: Bearer <token>`.",
)


def make_bearer_dependency(
    token: SecretStr,
) -> Callable[[HTTPAuthorizationCredentials | None], None]:
    """Build a FastAPI dependency that rejects requests without the expected token."""
    expected = token.get_secret_value().encode()

    def verify(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    ) -> None:
        supplied = credentials.credentials.encode() if credentials else b""
        if not hmac.compare_digest(supplied, expected):
            raise AuthenticationError("Invalid or missing token")

    return verify
