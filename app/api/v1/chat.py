import asyncio
import uuid
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.schemas.chat import ChatRequest
from app.utils.sse import format_sse


router = APIRouter(prefix="/chat", tags=["Chat"])
logger = logging.getLogger(__name__)


async def stream_chat_response(
    message: str,
    session_id: uuid.UUID,
    correlation_id: str,
):
    run_id = str(uuid.uuid4())

    try:
        yield format_sse(
            "session",
            {
                "session_id": str(session_id),
                "correlation_id": correlation_id,
            },
        )

        # Temporary streaming response for Day 2 testing
        for word in [
            "Your ",
            "query ",
            "has ",
            "been ",
            "received ",
            "successfully.",
        ]:
            yield format_sse("token", {"text": word})
            await asyncio.sleep(0.1)

        yield format_sse(
            "followups",
            {
                "chips": [
                    "Show available units",
                    "View project brochure",
                    "Show payment plan",
                ]
            },
        )

    except asyncio.CancelledError:
        raise

    except Exception:
        logger.exception(
            "Chat streaming failed | correlation_id=%s | session_id=%s",
            correlation_id,
            session_id,
        )

        yield format_sse(
            "error",
            {
                "code": "STREAM_ERROR",
                "message": "An unexpected error occurred.",
                "correlation_id": correlation_id,
            },
        )

    finally:
        # Real cleanup and logging will be added with session service.
        pass

    yield format_sse(
        "done",
        {
            "run_id": run_id,
            "correlation_id": correlation_id,
        },
    )

# @router.post("/query")
# async def chat_query(
#     body: ChatRequest,
#     request: Request,
#     current_user: dict = Depends(get_current_user),
# ) -> StreamingResponse:

@router.post("/query")
async def chat_query(
    body: ChatRequest,
    request: Request,
) -> StreamingResponse:

    authenticated_user_id = "123"
    correlation_id = request.state.correlation_id

    if body.user_id != authenticated_user_id:
        raise HTTPException(
            status_code=403,
            detail="User ID does not match authenticated user",
        )

    if body.start_conversation:
        session_id = uuid.uuid4()
    else:
        session_id = body.session_id

        # TODO: Verify session exists and belongs to the
        # authenticated user in PostgreSQL before streaming.
        # Until this is implemented, reject continuation requests.
        raise HTTPException(
            status_code=501,
            detail="Existing session lookup is not implemented yet",
        )

    return StreamingResponse(
        stream_chat_response(
            message=body.message,
            session_id=session_id,
            correlation_id=correlation_id,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Correlation-ID": correlation_id,
        },
    )