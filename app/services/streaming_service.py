import time
import asyncio
import logging
import uuid
import json
import re


from sqlalchemy.ext.asyncio import async_sessionmaker

from app.services.project_name_service import normalize_project_name
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
from app.retrieval.salesforce_client import SalesforceClient
from app.retrieval.inventory_connector import InventoryConnector
from app.services.inventory_catalog_service import InventoryCatalogService
from app.services.inventory_token_provider import get_inventory_token_service
from app.retrieval.project_name import resolve_project_name
from app.services.inventory_conversation_service import *
from app.core.keyvault import load_application_secrets


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

async def load_previous_inventory_context(
    clients,
    session_id,
    user_id,
):
    session_factory = async_sessionmaker(
        bind=clients.postgres,
        expire_on_commit=False,
        autoflush=False,
    )

    async with session_factory() as db:
        service = SessionService(db)

        return await service.get_latest_inventory_context(
            session_id=session_id,
            user_id=user_id,
        )

async def stream_chat_response(
    message: str,
    session_id: uuid.UUID,
    correlation_id: str,
    user_id: str,
    role: str,
    source: str,
    employee_type: str,
    clients: ServiceClients,
    access_token: str,
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

        secrets = await load_application_secrets()

        inventory_client = SalesforceClient(
            secrets=secrets
        )
        inventory_connector = InventoryConnector(
            salesforce_client=inventory_client
        )

        inventory_token_service = get_inventory_token_service(secrets=secrets)

        inventory_token = await inventory_token_service.get_token()

        inventory_snapshot = (
            await inventory_connector.fetch_inventory(
                token=inventory_token,
                user_id=user_id,
            )
        )

        previous_inventory_context = await load_previous_inventory_context(
            clients=clients,
            session_id=session_id,
            user_id=user_id,
        )

        previous_authorized_units = resolve_authorized_units(
            previous_inventory_context,
            inventory_snapshot,
        )

        previous_inventory_context = (
            {
                "project_name": previous_inventory_context.get("project_name"),
                "operation": previous_inventory_context.get("operation"),
                "unit_numbers": [
                    unit.unit_name
                    for unit in previous_authorized_units
                    if unit.unit_name
                ],
                "total_matches": len(previous_authorized_units),
            }
            if previous_inventory_context
            else None
        )


        active_project_names = list(
            dict.fromkeys(
                project.project_name
                for project in inventory_snapshot.projects
                if project.project_name
            )
        )

        logger.info(
            "ACTIVE_PROJECT_CATALOG_READY | count=%s",
            len(active_project_names),
        )

        inventory_catalogs = InventoryCatalogService.build(
            inventory_snapshot
        )

        available_projects = (
            await project_catalog_service.get_project_names()
        )

        if not available_projects:
            raise RuntimeError(
                "Project catalog is unavailable or empty"
            )

        active_project_names = active_project_names or []
        
        # LLM 1 receives the official project catalog
        routing_result = await router_service.classify(
            message=message,
            history=history,
            available_projects=available_projects,
            inventory_active_projects=inventory_catalogs.active_projects,
            inventory_unit_projects=inventory_catalogs.unit_projects,
            active_project_names=active_project_names,
            previous_inventory_context=previous_inventory_context,
        )

        for intent in routing_result.intents:

            if intent.intent != "inventory":
                continue

            if not previous_inventory_context:
                continue

            if intent.inventory_scope != "units":
                continue

            if intent.inventory_operation == "unit_comparison":

                previous_unit_numbers = previous_inventory_context.get(
                    "unit_numbers", []
                )

                if (
                    len(intent.compare_unit_numbers or []) < 2
                    and len(previous_unit_numbers) == 2
                ):

                    intent.compare_unit_numbers = list(
                        previous_unit_numbers
                    )

                    if not intent.project_name:
                        intent.project_name = (
                            previous_inventory_context.get("project_name")
                        )

                    resolved_fields = {"compare_unit_numbers"}

                    if intent.project_name:
                        resolved_fields.add("project_name")

                    intent.missing_fields = [
                        field
                        for field in intent.missing_fields
                        if field not in resolved_fields
                    ]

                    intent.requires_clarification = bool(
                        intent.missing_fields
                    )

                    print(
                        "\n========== INVENTORY FOLLOW-UP DEBUG ==========",
                        "\nOperation:", intent.inventory_operation,
                        "\nProject:", intent.project_name,
                        "\nUnits:", intent.compare_unit_numbers,
                        "\nRequires clarification:",
                        intent.requires_clarification,
                        "\n===============================================",
                    )
                    

        for intent in routing_result.intents:

            if intent.intent not in {
                "project_information",
                "inventory",
            }:
                continue

            if not intent.project_name:
                continue

            resolved_name = resolve_project_name(
                requested_name=intent.project_name,
                available_projects=active_project_names,
            )

            if resolved_name:
                intent.project_name = resolved_name

                # Clear stale project-name clarification.
                intent.missing_fields = [
                    field
                    for field in intent.missing_fields
                    if field != "project_name"
                ]

                if not intent.missing_fields:
                    intent.requires_clarification = False

            else:
                intent.requires_clarification = True

                if "project_name" not in intent.missing_fields:
                    intent.missing_fields.append("project_name")


        marketing_names = set(available_projects)

        inventory_active_names = set(
            inventory_catalogs.active_projects
        )

        inventory_unit_names = set(
            inventory_catalogs.unit_projects
        )

        # Map normalized marketing names to canonical names.
        marketing_name_lookup = {}

        for name in available_projects:
            key = normalize_project_name(name)
            marketing_name_lookup.setdefault(key, []).append(name)

        def resolve_visible_unit_project(user_message: str):
            matches = []

            for unit in inventory_snapshot.units:
                identifiers = [
                    unit.unit_id,
                    unit.unit_name,
                ]

                for identifier in identifiers:
                    if not identifier:
                        continue

                    pattern = (
                        r"(?<![A-Za-z0-9])"
                        + re.escape(str(identifier))
                        + r"(?![A-Za-z0-9])"
                    )

                    if re.search(
                        pattern,
                        user_message,
                        flags=re.IGNORECASE,
                    ):
                        matches.append(unit)
                        break

            unique_projects = {
                normalize_project_name(unit.project_name)
                for unit in matches
                if unit.project_name
            }

            if len(unique_projects) != 1:
                return None

            return matches[0].project_name
        

        # Tracks intents that must not execute.
        blocked_intents = set()

        for index, intent in enumerate(routing_result.intents):

            if intent.intent == "marketing":
                
                resolved_project = resolve_visible_unit_project(
                    message
                )

                if resolved_project:
                    intent.project_name = resolved_project

                if intent.project_name:

                    key = normalize_project_name(
                        intent.project_name
                    )

                    candidates = marketing_name_lookup.get(
                        key, []
                    )

                    if len(candidates) == 1:
                        intent.project_name = candidates[0]

                        intent.missing_fields = [
                            field
                            for field in intent.missing_fields
                            if field != "project_name"
                        ]

                        intent.requires_clarification = bool(
                            intent.missing_fields
                        )

                    elif len(candidates) > 1:
                        intent.requires_clarification = True

                        if "project_name" not in intent.missing_fields:
                            intent.missing_fields.append(
                                "project_name"
                            )

                valid_names = marketing_names

            elif intent.intent == "inventory":

                if intent.inventory_scope == "projects":
                    valid_names = inventory_active_names

                elif intent.inventory_scope == "units":
                    # Accept recognized projects even when
                    # no units are visible for that project.
                    valid_names = (
                        inventory_active_names
                        | inventory_unit_names
                    )

                else:
                    intent.requires_clarification = True
                    blocked_intents.add(index)
                    continue

            else:
                # Preserve current validation behavior for
                # other intents until their own catalogs exist.
                valid_names = marketing_names

            if intent.project_name is not None:

                normalized_requested = normalize_project_name(
                    intent.project_name
                )

                matches = [
                    name
                    for name in valid_names
                    if normalize_project_name(name)
                    == normalized_requested
                ]

                if len(matches) == 1:
                    intent.project_name = matches[0]

                    # Remove stale project-name clarification.
                    intent.missing_fields = [
                        field
                        for field in intent.missing_fields
                        if field != "project_name"
                    ]

                    if not intent.missing_fields:
                        intent.requires_clarification = False

                elif len(matches) == 0:
                    intent.requires_clarification = True
                    blocked_intents.add(index)

                    if "project_name" not in intent.missing_fields:
                        intent.missing_fields.append("project_name")

                else:
                    # Multiple catalog entries match the same normalized name.
                    # Do not guess which project was intended.
                    intent.requires_clarification = True
                    blocked_intents.add(index)

                    if "project_name" not in intent.missing_fields:
                        intent.missing_fields.append("project_name")

            # Block ambiguous or incomplete requests.
            if intent.requires_clarification:
                blocked_intents.add(index)

        routing_result.requires_clarification = any(
            item.requires_clarification
            for item in routing_result.intents
        )


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
            redis_client=clients.redis,
            inventory_snapshot=inventory_snapshot,
        )

        handler_results = []
        clarification_messages = []

        # 4. PROCESS CLASSIFIED INTENTS

        for index, intent in enumerate(routing_result.intents):

            # FIX 3: Do not execute unresolved intents.
            if index in blocked_intents:

                clarification_messages.append(
                    "Please clarify the project or "
                    "details for your request."
                )

                logger.info(
                    "INTENT_BLOCKED_FOR_CLARIFICATION | "
                    "intent=%s | correlation_id=%s",
                    intent.intent,
                    correlation_id,
                )

                continue

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
        response_messages = list(clarification_messages)
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
                logger.info(
                    "GENERATION_CONTEXT_READY | "
                    "service=%s | operation=%s | match_status=%s",
                    result.generation_context.get("service"),
                    result.generation_context.get("operation"),
                    result.generation_context.get("match_status"),
                )


        # 5. BUILD RESPONSE USING LLM 2

        inventory_html_only = (
            len(routing_result.intents) == 1
            and routing_result.intents[0].intent == "inventory"
            and routing_result.intents[0].inventory_operation
                in {"unit_search", "unit_comparison"}
            and not clarification_messages
            and any(
                block.get("card_type") in {
                    "inventory_listing",
                    "inventory_comparison",
                }
                for block in all_html_blocks
            )
            and all(
                context.get("match_status") not in {
                    "partial",
                    "none",
                    "no_exact_matches",
                }
                for context in generation_contexts
            )
        )

        llm2_used = False

        if generation_contexts:

            # Preserve the existing single-intent context.
            if len(generation_contexts) == 1:
                generation_context = generation_contexts[0]
            else:
                # Supports multiple successful intents.
                generation_context = {
                    "service": "multi_intent",
                    "results": generation_contexts,
                }

            # LLM 2 still runs for dynamic follow-up chips.
            generation_result = await generation_service.generate(
                message=message,
                language=routing_result.language,
                intents=detected_intents,
                service_results=generation_context,
                history=history,
            )

            llm2_used = True

            followup_chips = generation_result.followups

            response_text = (generation_result.response or "").strip()

            # Preserve clarification and other messages.
            if response_messages:
                response_text = " ".join(
                    [response_text, *response_messages]
                ).strip()

        else:

            if response_messages:
                response_text = " ".join(response_messages)
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
            "inventory_html_only=%s | "
            "chips=%s",
            correlation_id,
            llm2_used,
            inventory_html_only,
            len(followup_chips),
        )

        # 5A. PREPARE TEXT FOR DATABASE PERSISTENCE

        display_response_text = response_text.strip()

        # Ensure that the assistant message is never empty.
        if not display_response_text:
            if all_html_blocks:
                display_response_text = (
                    "I found the requested information. "
                    "You can view the details below."
                )
            else:
                display_response_text = (
                    "I couldn't find the requested information."
                )

        persist_response_text = display_response_text
        response_text = display_response_text

        # 6. BUILD FINAL RESPONSE

        final_response = ChatResponse(
            response=display_response_text,
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

        new_inventory_context = None
        for intent, result in zip(
            [
                intent
                for index, intent in enumerate(routing_result.intents)
                if index not in blocked_intents
            ],
            handler_results,
        ):
            candidate = build_inventory_context(
                intent=intent,
                handler_result=result,
                inventory_snapshot=inventory_snapshot,
            )

            if candidate:
                new_inventory_context = candidate

        response_payload = {
            "version": 1,
            "html_blocks": saved_html_blocks,
            "files": final_response.model_dump(mode="json")["data"]["files"],
            "followups": final_response.model_dump(mode="json")["followups"],
            "inventory_context": new_inventory_context,

        }

        
        latency_ms = int(
            (time.perf_counter() - started_at) * 1000
        )

        saved_records = await persist_completed_chat(
            clients=clients,
            session_id=session_id,
            user_id=user_id,
            user_message=message,
            assistant_message=persist_response_text,
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

        if response_text.strip():
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
        print(f"[STREAM DEBUG] Error code: {getattr(exc, 'error_code', 'N/A')}",flush=True)

        error_code = getattr(
            exc,
            "error_code",
            "UPSTREAM_SERVICE_ERROR",
        )

        traceback.print_exc()

        if error_code == "INVENTORY_RATE_LIMITED":

            user_message = (
                "The property information service is temporarily "
                "busy due to high demand. "
                "Please try again in a little while."
            )

            response_code = "INVENTORY_RATE_LIMITED"
            retryable = True

        else:

            user_message = (
                "The response could not be completed. "
                "Please try again."
            )

            response_code = "UPSTREAM_SERVICE_ERROR"
            retryable = True

        error_response = ErrorResponse(
            error=ErrorDetail(
                code=response_code,
                message=user_message,
                session_id=str(session_id),
                correlation_id=correlation_id,
                retryable=retryable,
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
