import uuid
from contextvars import ContextVar

from fastapi import Request

correlation_id_ctx: ContextVar[str | None] = ContextVar(
    "correlation_id",
    default=None,
)


async def correlation_id_middleware(request: Request, call_next):
    incoming_id = request.headers.get("X-Correlation-ID")

    try:
        correlation_id = str(uuid.UUID(incoming_id))
    except (ValueError, TypeError, AttributeError):
        correlation_id = str(uuid.uuid4())

    token = correlation_id_ctx.set(correlation_id)
    request.state.correlation_id = correlation_id

    try:
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        return response
    finally:
        correlation_id_ctx.reset(token)