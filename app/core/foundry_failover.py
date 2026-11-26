
"""
Automatic failover between two Microsoft Foundry deployments.

Normal request:
    Primary Foundry

If primary returns HTTP 429:
    Retry the same request using Secondary Foundry

Supports:
    responses.parse()
    responses.create()
    responses.stream()
"""

import asyncio
import logging

from contextlib import AsyncExitStack, asynccontextmanager

from openai import (
    AsyncOpenAI,
    RateLimitError,
    InternalServerError,
    APIConnectionError,
    APITimeoutError,
)


logger = logging.getLogger(__name__)

FAILOVER_EXCEPTIONS = (
    RateLimitError,
    InternalServerError,
    APIConnectionError,
    APITimeoutError,
)


class FailoverResponses:
    """
    Preserve the OpenAI Responses API interface
    while adding automatic failover on HTTP 429.
    """

    def __init__(
        self,
        primary: AsyncOpenAI,
        secondary: AsyncOpenAI,
    ):
        self.primary = primary
        self.secondary = secondary

    async def parse(self, **kwargs):
        """
        Used for structured-output LLM requests.
        """

        try:
            return await self.primary.responses.parse(
                **kwargs
            )

        except FAILOVER_EXCEPTIONS as exc:
            logger.warning(
                "FOUNDRY_FAILOVER | "
                "operation=parse | "
                "error_type=%s | "
                "status_code=%s | "
                "switching_to=secondary",
                type(exc).__name__,
                getattr(exc, "status_code", None),
            )

            return await self.secondary.responses.parse(
                **kwargs
            )

    async def create(self, **kwargs):
        """
        Used for normal Responses API requests.
        """

        try:
            return await self.primary.responses.create(
                **kwargs
            )

        except FAILOVER_EXCEPTIONS as exc:
            logger.warning(
                "FOUNDRY_FAILOVER | "
                "operation=create | "
                "error_type=%s | "
                "status_code=%s | "
                "switching_to=secondary",
                type(exc).__name__,
                getattr(exc, "status_code", None),
            )

            return await self.secondary.responses.create(
                **kwargs
            )

    @asynccontextmanager
    async def stream(self, **kwargs):
        """
        Used for SSE / real-time LLM streaming.

        Failover is allowed only while opening the stream.
        Once streaming begins, the request is not replayed
        on another deployment.
        """

        async with AsyncExitStack() as stack:

            try:
                stream = await stack.enter_async_context(
                    self.primary.responses.stream(
                        **kwargs
                    )
                )

            except FAILOVER_EXCEPTIONS as exc:
                logger.warning(
                    "FOUNDRY_FAILOVER | "
                    "operation=stream | "
                    "error_type=%s | "
                    "status_code=%s | "
                    "switching_to=secondary",
                    type(exc).__name__,
                    getattr(exc, "status_code", None),
                )

                stream = await stack.enter_async_context(
                    self.secondary.responses.stream(
                        **kwargs
                    )
                )

            yield stream


class FailoverChatCompletions:
    """
    Handle Chat Completions API requests
    with automatic failover on HTTP 429.
    """

    def __init__(
        self,
        primary: AsyncOpenAI,
        secondary: AsyncOpenAI,
    ):
        self.primary = primary
        self.secondary = secondary

    async def create(self, **kwargs):

        try:
            return await self.primary.chat.completions.create(
                **kwargs
            )

        except FAILOVER_EXCEPTIONS as exc:
            logger.warning(
                "FOUNDRY_FAILOVER | "
                "operation=chat.completions.create | "
                "error_type=%s | "
                "status_code=%s | "
                "switching_to=secondary",
                type(exc).__name__,
                getattr(exc, "status_code", None),
            )

            return await self.secondary.chat.completions.create(
                **kwargs
            )


class FailoverChat:
    def __init__(
        self,
        primary: AsyncOpenAI,
        secondary: AsyncOpenAI,
    ):
        self.completions = FailoverChatCompletions(
            primary=primary,
            secondary=secondary,
        )


class FoundryFailoverClient:
    """
    Shared client passed to existing chatbot services.

    Existing usage stays the same:

        client.responses.parse(...)
        client.responses.create(...)
        client.responses.stream(...)
    """

    def __init__(
        self,
        primary: AsyncOpenAI,
        secondary: AsyncOpenAI,
    ):
        self.primary = primary
        self.secondary = secondary

        self.responses = FailoverResponses(
            primary=primary,
            secondary=secondary,
        )
        self.chat = FailoverChat(
            primary=primary,
            secondary=secondary,
        )


    async def close(self):
        """
        Close both HTTP clients on shutdown.
        """

        await asyncio.gather(
            self.primary.close(),
            self.secondary.close(),
        )
