import time
import asyncio
import logging
import uuid
import json

from sqlalchemy.ext.asyncio import async_sessionmaker


from app.core.config import get_settings
from app.core.clients import ServiceClients
from app.schemas.chat import ChatResponse
from app.schemas.streaming import HTMLBlockEvent
from app.schemas.errors import ErrorResponse, ErrorDetail
from app.services.router_service import RouterService
from app.services.session_service import SessionService
from app.services.generation_service import GenerationService, build_marketing_generation_context
from app.utils.sse import format_sse
from app.services.project_catalog_service import ProjectCatalogService
from app.handlers.dispatcher import IntentDispatcher
from app.persistence.redis_store import RedisCacheKeys


logger = logging.getLogger(__name__)
settings = get_settings()



async def persist_completed_chat(
    clients,
    session_id,
    user_id,
    user_message,
    assistant_message,
    intents,
    latency_ms,
    response_payload: dict | None = None,
):
    """
    Persist a completed chatbot exchange using
    the existing SessionService.

    Includes structured response data for
    frontend chat history restoration.
    """

    session_factory = async_sessionmaker(
        bind=clients.postgres,
        expire_on_commit=False,
        autoflush=False,
    )

    async with session_factory() as db:

        service = SessionService(db)

        return await service.save_completed_exchange(
            session_id=session_id,
            user_id=user_id,
            user_message=user_message,
            assistant_message=assistant_message,
            intents=intents,
            latency_ms=latency_ms,
            response_payload=response_payload,
        )

async def load_chat_history(
    clients,
    session_id,
    user_id,
    limit=10,
):
    """
    Retrieve recent conversation messages
    from PostgreSQL.
    """

    session_factory = async_sessionmaker(
        bind=clients.postgres,
        expire_on_commit=False,
        autoflush=False,
    )

    async with session_factory() as db:

        service = SessionService(db)

        history = await service.get_recent_context(
            session_id=session_id,
            user_id=user_id,
            message_limit=limit,
        )

        return history


async def stream_chat_response(
    message: str,
    session_id: uuid.UUID,
    correlation_id: str,
    user_id: str,
    role: str,
    source: str,
    clients: ServiceClients,
):

    started_at = time.perf_counter()

    status = "failed"

    logger.info(
        "Chat stream started | correlation_id=%s | session_id=%s",
        correlation_id,
        session_id,
    )

    try:
        # 1. SESSION EVENT

        yield format_sse(
            "session",
            {
                "session_id": str(session_id),
                "correlation_id": correlation_id,
            },
        )

        # 2. CLASSIFY USER QUERY

        settings = get_settings()

        router_service = RouterService(
            client=clients.foundry_openai,
            model=settings.foundry_openai_model,
        )

        history = await load_chat_history(
            clients=clients,
            session_id=session_id,
            user_id=user_id,
            limit=10,
        )


        # Load official project names from Redis
        project_catalog_service = ProjectCatalogService(
            redis_client=clients.redis,
        )

        available_projects = (
            await project_catalog_service.get_project_names()
        )


        project_catalog_service = ProjectCatalogService(
            redis_client=clients.redis,
        )

        available_projects = (
            await project_catalog_service.get_project_names()
        )

        if not available_projects:
            raise RuntimeError(
                "Project catalog is unavailable or empty"
            )
        
        # LLM 1 receives the official project catalog
        routing_result = await router_service.classify(
            message=message,
            history=history,
            available_projects=available_projects,
        )

        valid_projects = set(available_projects)
        for intent in routing_result.intents:

            if (
                intent.project_name
                and intent.project_name not in valid_projects
            ):
                logger.warning(
                    "INVALID_PROJECT_SELECTION | "
                    "intent=%s | project=%s | "
                    "correlation_id=%s",
                    intent.intent,
                    intent.project_name,
                    correlation_id,
                )

                intent.project_name = None

        detected_intents = [
            item.intent
            for item in routing_result.intents
        ]

        logger.info(
            "ROUTER_RESULT | correlation_id=%s | "
            "intents=%s | clarification=%s",
            correlation_id,
            detected_intents,
            routing_result.requires_clarification,
        )

        generation_service = GenerationService(
            client=clients.foundry_openai,
            model=(
                settings.generation_openai_model
                or settings.foundry_openai_model
            ),
        )
                
        
        # 3. INITIALIZE INTENT DISPATCHER

        dispatcher = IntentDispatcher(
            redis_client=clients.redis
        )

        handler_results = []

        # 4. PROCESS CLASSIFIED INTENTS

        for intent in routing_result.intents:

            result = await dispatcher.execute(intent)

            handler_results.append(result)

            logger.info(
                "INTENT_EXECUTED | "
                "correlation_id=%s | "
                "intent=%s | "
                "has_data=%s | "
                "html_blocks=%s",
                correlation_id,
                intent.intent,
                result.has_data,
                len(result.html_blocks),
            )

        # 4A. COMBINE HANDLER RESULTS

        all_html_blocks = []
        all_files = []
        response_messages = []
        generation_contexts = []

        for result in handler_results:

            all_html_blocks.extend(
                result.html_blocks
            )

            all_files.extend(
                result.files
            )

            response_messages.extend(
                result.messages
            )

            if result.has_data:
                generation_contexts.append(
                    result.generation_context
                )


        # 5. BUILD RESPONSE USING LLM 2

        if generation_contexts:

            # Preserve the existing single-marketing
            # context shape for the current LLM 2 prompt.
            if len(generation_contexts) == 1:
                generation_context = (
                    generation_contexts[0]
                )
            else:
                # Supports multiple successful intents.
                generation_context = {
                    "service": "multi_intent",
                    "results": generation_contexts,
                }

            generation_result = (
                await generation_service.generate(
                    message=message,
                    language=routing_result.language,
                    intents=detected_intents,
                    service_results=generation_context,
                    history=history,
                )
            )

            response_text = generation_result.response
            followup_chips = generation_result.followups

            if response_messages:
                response_text = " ".join(
                    [response_text, *response_messages]
                )

        else:

            if response_messages:
                response_text = " ".join(
                    response_messages
                )
            else:
                response_text = (
                    "I couldn't find the requested "
                    "information. Please try specifying "
                    "a Danube project and what you need."
                )

            followup_chips = []

        logger.info(
            "RESPONSE_PREPARED | "
            "correlation_id=%s | "
            "llm2_used=%s | "
            "chips=%s",
            correlation_id,
            bool(generation_contexts),
            len(followup_chips),
        )


        # 6. BUILD FINAL RESPONSE

        final_response = ChatResponse(
            response=response_text,
            session_id=session_id,
            correlation_id=correlation_id,
            followups=followup_chips,
            data={
                "files": all_files,
                "classification": (
                    routing_result.model_dump(mode="json")
                ),
            },
        )

        # 7. SAVE TO POSTGRESQL FIRST

        saved_html_blocks = [
            HTMLBlockEvent(
                card_type=block["card_type"],
                html=block["html"],
            ).model_dump(mode="json")
            for block in all_html_blocks
        ]
        response_payload = {
            "version": 1,
            "html_blocks": saved_html_blocks,
            "files": final_response.model_dump(
                mode="json"
            )["data"]["files"],
            "followups": final_response.model_dump(
                mode="json"
            )["followups"],
        }

        
        latency_ms = int(
            (time.perf_counter() - started_at) * 1000
        )

        saved_records = await persist_completed_chat(
            clients=clients,
            session_id=session_id,
            user_id=user_id,
            user_message=message,
            assistant_message=response_text,
            intents=detected_intents,
            latency_ms=latency_ms,
            response_payload=response_payload,
        )

        logger.info(
            "CHAT_PERSISTED | "
            "session_id=%s | "
            "correlation_id=%s | "
            "records=%s",
            session_id,
            correlation_id,
            saved_records,
        )

        # 8. STREAM GENERATED RESPONSE TEXT

        for word in response_text.split(" "):
            yield format_sse(
                "token",
                {"text": word + " "},
            )

            await asyncio.sleep(0.02)

        # 9. STREAM HTML BLOCKS

        for block in all_html_blocks:

            html_event = HTMLBlockEvent(
                card_type=block["card_type"],
                html=block["html"],
            )

            yield format_sse(
                "html_block",
                html_event.model_dump(mode="json"),
            )

        # 10. FOLLOW-UP CHIPS

        yield format_sse(
            "followups",
            {"chips": followup_chips},
        )

        # 11. FINAL RESPONSE EVENT

        final_payload = final_response.model_dump(
            mode="json"
        )
        yield format_sse(
            "final",
            final_payload,
        )

        status = "completed"


        logger.info(
            "Chat stream completed | "
            "correlation_id=%s | "
            "session_id=%s | "
            "html_blocks=%s",
            correlation_id,
            session_id,
            len(all_html_blocks),
        )

    except asyncio.CancelledError:
        raise

    except Exception as exc:
        import traceback

        print("\n" + "=" * 70, flush=True)
        print("[STREAM DEBUG] EXCEPTION OCCURRED", flush=True)
        print(f"[STREAM DEBUG] Exception type: {type(exc).__name__}", flush=True)
        print(f"[STREAM DEBUG] Exception message: {exc}", flush=True)
        print(f"[STREAM DEBUG] Correlation ID: {correlation_id}", flush=True)
        print("[STREAM DEBUG] FULL TRACEBACK:", flush=True)

        traceback.print_exc()

        print("=" * 70 + "\n", flush=True)


        error_response = ErrorResponse(
            error=ErrorDetail(
                code="UPSTREAM_SERVICE_ERROR",
                message=(
                    "The response could not be completed. "
                    "Please try again."
                ),
                session_id=str(session_id),
                correlation_id=correlation_id,
                retryable=True,
            )
        )

        yield format_sse(
            "error",
            error_response.model_dump(
                mode="json"
            ),
        )

    # 12. DONE EVENT

    yield format_sse(
        "done",
        {
            "status": status,
        },
    )
