# import uuid
# import logging

# from fastapi import APIRouter, HTTPException, Request
# from fastapi.responses import StreamingResponse

# from app.schemas.chat import ChatRequest
# from app.services.streaming_service import stream_chat_response
# from app.services.api_cache_service import *


# router = APIRouter(prefix="/chat", tags=["Chat"])
# logger = logging.getLogger(__name__)


# @router.post("/query")
# async def chat_query(
#     body: ChatRequest,
#     request: Request,
# ) -> StreamingResponse:

#     correlation_id = request.state.correlation_id

#     logger.warning(
#         "DANUBE_CHAT_API_TEST | correlation_id=%s",
#         correlation_id,
#     )

#     user_id = body.user_id

#     # 1. Log incoming validated request
#     logger.info(
#         "Chat API request received",
#         extra={
#             "custom_dimensions": {
#                 "correlation_id": correlation_id,
#                 "source": body.source,
#                 "start_conversation": body.start_conversation,
#             }
#         },
#     )

#     # 2. Session handling
#     if body.start_conversation:
#         session_id = uuid.uuid4()

#         logger.info(
#             "New chat session created",
#             extra={
#                 "custom_dimensions": {
#                     "correlation_id": correlation_id,
#                     "session_id": str(session_id),
#                 }
#             },
#         )

#     else:
#         session_id = body.session_id

#         logger.warning(
#             "Existing chat session not implemented",
#             extra={
#                 "custom_dimensions": {
#                     "correlation_id": correlation_id,
#                     "session_id": str(session_id),
#                 }
#             },
#         )

#         raise HTTPException(
#             status_code=501,
#             detail="Existing session lookup is not implemented yet",
#         )

#     # 3. Return SSE response
#     return StreamingResponse(
#         stream_chat_response(
#             message=body.message,
#             session_id=session_id,
#             correlation_id=correlation_id,
#             user_id=user_id,
#             role=body.role,
#             source=body.source,
#         ),
#         media_type="text/event-stream",
#         headers={
#             "Cache-Control": "no-cache",
#             "X-Accel-Buffering": "no",
#             "X-Correlation-ID": correlation_id,
#         },
#     )


import uuid
import json
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.schemas.chat import ChatRequest
from app.services.streaming_service import stream_chat_response
from app.services.api_cache_service import APICacheService
from app.persistence.redis_store import RedisCacheKeys


router = APIRouter(prefix="/chat", tags=["Chat"])
logger = logging.getLogger(__name__)

ENABLE_REDIS_TEST = True


@router.post("/query")
async def chat_query(
    body: ChatRequest,
    request: Request,
) -> StreamingResponse:

    correlation_id = request.state.correlation_id

    logger.warning(
        "DANUBE_CHAT_API_TEST | correlation_id=%s",
        correlation_id,
    )

    user_id = body.user_id

    # 1. Log incoming validated request
    logger.info(
        "Chat API request received",
        extra={
            "custom_dimensions": {
                "correlation_id": correlation_id,
                "source": body.source,
                "start_conversation": body.start_conversation,
            }
        },
    )

    # 2. Session handling
    if body.start_conversation:
        session_id = uuid.uuid4()

        logger.info(
            "New chat session created",
            extra={
                "custom_dimensions": {
                    "correlation_id": correlation_id,
                    "session_id": str(session_id),
                }
            },
        )

    else:
        session_id = body.session_id

        logger.warning(
            "Existing chat session not implemented",
            extra={
                "custom_dimensions": {
                    "correlation_id": correlation_id,
                    "session_id": str(session_id),
                }
            },
        )

        raise HTTPException(
            status_code=501,
            detail="Existing session lookup is not implemented yet",
        )

    # 3. TEMPORARY REDIS CACHE TEST
    if ENABLE_REDIS_TEST and body.message in (
        "__test_redis_marketing__",
        "__test_redis_currency__",
    ):

        redis_client = request.app.state.clients.redis
        cache = APICacheService(redis_client)

        if body.message == "__test_redis_marketing__":
            api_name = "marketing"
            cache_key = RedisCacheKeys.MARKETING_CATALOG

        else:
            api_name = "currency"
            cache_key = RedisCacheKeys.CURRENCY_RATES

        # Read directly from Redis.
        # No live API call is made here.
        cached_response = await cache.get(cache_key)

        cache_hit = cached_response is not None

        data = (
            cached_response.get("data")
            if isinstance(cached_response, dict)
            else None
        )

        remaining_ttl = await redis_client.ttl(cache_key)

        result = {
            "api": api_name,
            "source": "redis",
            "cache_hit": cache_hit,
            "cache_key": cache_key,
            "last_refreshed": (
                cached_response.get("refreshed_at")
                if isinstance(cached_response, dict)
                else None
            ),
            "remaining_ttl_seconds": remaining_ttl,
            "data_type": (
                type(data).__name__
                if data is not None
                else None
            ),
            "top_level_fields": (
                list(data.keys())
                if isinstance(data, dict)
                else []
            ),
        }

        logger.info(
            "CHAT_REDIS_TEST | api=%s | cache_hit=%s | "
            "correlation_id=%s",
            api_name,
            cache_hit,
            correlation_id,
        )

        async def redis_test_stream():

            yield (
                "event: cache_test\n"
                f"data: {json.dumps(result)}\n\n"
            )

            yield (
                "event: done\n"
                'data: {"status":"completed"}\n\n'
            )

        return StreamingResponse(
            redis_test_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "X-Correlation-ID": correlation_id,
            },
        )

    # 4. Normal chatbot SSE response
    return StreamingResponse(
        stream_chat_response(
            message=body.message,
            session_id=session_id,
            correlation_id=correlation_id,
            user_id=user_id,
            role=body.role,
            source=body.source,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Correlation-ID": correlation_id,
        },
    )
