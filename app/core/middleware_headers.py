
from contextvars import ContextVar
from typing import Mapping


MIDDLEWARE_SOURCE = "Danube -one-chat"

_current_user_id: ContextVar[str | None] = ContextVar(
    "middleware_user_id",
    default=None,
)

_current_salesforce_token: ContextVar[str | None] = ContextVar(
    "middleware_salesforce_token",
    default=None,
)


def set_middleware_context(
    user_id: str,
    salesforce_token: str,
):
    """Set authenticated details for this chatbot request."""

    if not user_id or not user_id.strip():
        raise ValueError("Authenticated user_id is missing")

    if not salesforce_token or not salesforce_token.strip():
        raise ValueError("Salesforce token is missing")

    user_token = _current_user_id.set(user_id.strip())
    auth_token = _current_salesforce_token.set(
        salesforce_token.strip()
    )

    return user_token, auth_token


def reset_middleware_context(tokens):
    """Clear request-specific details after processing."""
    user_token, auth_token = tokens

    _current_salesforce_token.reset(auth_token)
    _current_user_id.reset(user_token)


def build_middleware_headers(
    existing_headers: Mapping[str, str] | None = None,
    *,
    require_user_context: bool = True,
) -> dict[str, str]:
    """
    Add middleware headers without removing existing ones.

    For authenticated API calls, require both user_id
    and Salesforce token.

    Background jobs can use require_user_context=False,
    but must have a separate authentication strategy
    if middleware requires these headers.
    """

    headers = dict(existing_headers or {})

    user_id = _current_user_id.get()
    salesforce_token = _current_salesforce_token.get()

    headers["source"] = MIDDLEWARE_SOURCE

    if require_user_context:
        if not user_id or not salesforce_token:
            raise ValueError(
                "Middleware request context is missing "
                "user_id or Salesforce token"
            )

    if user_id and salesforce_token:
        headers["user_id"] = user_id
        headers["salesforce_access_token"] = salesforce_token

    return headers
