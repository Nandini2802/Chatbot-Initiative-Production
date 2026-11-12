import logging
import uuid

from fastapi import APIRouter, HTTPException, Request, Depends, Header
from fastapi.responses import StreamingResponse
from typing import Annotated
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.schemas.chat import ChatRequest
from app.services.streaming_service import stream_chat_response
from app.services.walkthrough_access_service import granted_feature_keys
from app.core.dependencies import get_session_service
from app.services.session_service import SessionService, SessionNotFoundError, SessionResumeRequiredError
from app.observability.logger import audit_event

router = APIRouter(
    prefix="/chat",
    tags=["Chat"],
)

bearer_scheme = HTTPBearer(
    auto_error=False,
    description="Enter the access token issued by Danube authentication."
)

logger = logging.getLogger(__name__)


def logged_key_features(value: str | None) -> tuple[str, int]:
    """
    Feature keys as received, for the request log:
      ("<not sent>", 0)                - no key_features in the request (or null)
      ("<empty>", 0)                   - key_features sent but blank
      ("dardashboard,udpage", 2)       - compacted, sorted keys, as the
                                         walkthrough check compares them
    Returned as one string (plus a count) so long lists are not cut
    to the logger's 20-item list limit.
    """
    if value is None:
        return "<not sent>", 0

    keys = sorted(granted_feature_keys(value))

    if not keys:
        return "<empty>", 0

    return ",".join(keys), len(keys)


@router.post("/query")
async def chat_query(
    body: ChatRequest,
    request: Request,
    session_service: Annotated[
        SessionService,
        Depends(get_session_service),
    ],
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme)
    ],

) -> StreamingResponse:

    if credentials is None or not credentials.credentials.strip():
        raise HTTPException(
            status_code=401,
            detail="Authorization token is required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="Bearer authentication is required",
            headers={"WWW-Authenticate": "Bearer"},
        )


    correlation_id = getattr(
        request.state,
        "correlation_id",
        str(uuid.uuid4()),
    )

    clients = request.app.state.clients

    key_features_logged, key_features_count = logged_key_features(
        body.key_features
    )

    audit_event(
        "CHAT_REQUEST_RECEIVED",
        correlation_id=correlation_id,
        user_id=body.user_id,
        role=body.role,
        source=body.source,
        user_message=body.message,
        start_conversation=body.start_conversation,
        session_id=str(body.session_id) if body.session_id else None,
        # Feature keys exactly as received (compacted, as compared by
        # the walkthrough check). Key names are not sensitive.
        key_features=key_features_logged,
        key_features_count=key_features_count,
    )

    # 1. SESSION HANDLING

    if body.start_conversation:

        session = await session_service.create_session(
            user_id=body.user_id,
            user_role=body.role,
            source=body.source,
            title=body.message.strip()[:100],
        )

        session_id = session.id

        logger.info(
            "CHAT_SESSION_CREATED | "
            "correlation_id=%s | "
            "session_id=%s",
            correlation_id,
            session_id,
        )

    else:

        if body.session_id is None:
            raise HTTPException(
                status_code=422,
                detail="session_id is required",
            )

        try:
            await session_service.admit_chat_message(
                session_id=body.session_id,
                user_id=body.user_id,
                inactivity_minutes=30,
            )

        except SessionResumeRequiredError:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "SESSION_RESUME_REQUIRED",
                    "message": (
                        "Your previous conversation has been "
                        "inactive for 30 minutes. "
                        "Please choose Continue or New Chat."
                    ),
                    "session_id": str(body.session_id),
                },
            )

        except SessionNotFoundError:
            raise HTTPException(
                status_code=404,
                detail="Session not found",
            )

        session_id = body.session_id

        logger.info(
            "CHAT_SESSION_RESUMED | "
            "session_id=%s | correlation_id=%s",
            session_id,
            correlation_id,
        )

    audit_event(
        "CHAT_SESSION_READY",
        correlation_id=correlation_id,
        session_id=str(session_id),
        user_id=body.user_id,
        status="ready",
    )

    # 2. NORMAL CHATBOT STREAMING

    return StreamingResponse(
        stream_chat_response(
            message=body.message,
            session_id=session_id,
            correlation_id=correlation_id,
            user_id=body.user_id,
            role=body.role,
            source=body.source,
            employee_type=body.employee_type,
            clients=clients,
            access_token=credentials.credentials.strip(),
            walkthrough_engine=request.app.state.walkthrough_engine,
            key_features=body.key_features,
            selected_payment_plan_names=body.selected_payment_plan_names,
            selected_payment_plan=body.selected_payment_plan,
            action=body.action,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Correlation-ID": correlation_id,
        },
    )
