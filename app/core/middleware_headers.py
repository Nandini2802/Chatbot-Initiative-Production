
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
    Build headers for middleware API requests.

    User-specific APIs:
        Require user_id and Salesforce token.

    Public/service APIs:
        Can explicitly disable user context.
    """

    headers = dict(existing_headers or {})

    headers["source"] = MIDDLEWARE_SOURCE

    if not require_user_context:
        for key in list(headers):
            if key.lower() in (
                "user_id",
                "salesforce_access_token",
            ):
                headers.pop(key)

        return headers

    user_id = _current_user_id.get()
    salesforce_token = _current_salesforce_token.get()

    if not user_id or not salesforce_token:
        raise ValueError(
            "Middleware request context is missing "
            "user_id or Salesforce token"
        )

    headers["user_id"] = user_id
    headers["salesforce_access_token"] = salesforce_token

    return headers

