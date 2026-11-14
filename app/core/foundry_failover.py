
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

from openai import AsyncOpenAI, RateLimitError


logger = logging.getLogger(__name__)


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

        except RateLimitError:
            logger.warning(
                "FOUNDRY_RATE_LIMIT | "
                "operation=parse | "
                "primary=429 | "
                "switching_to=secondary"
            )

            return await self.secondary.responses.parse(
                **kwargs
            )

    async def create(self, **kwargs):
        """
        Used for normal Responses API requests,
        including the startup Foundry check.
        """

        try:
            return await self.primary.responses.create(
                **kwargs
            )

        except RateLimitError:
            logger.warning(
                "FOUNDRY_RATE_LIMIT | "
                "operation=create | "
                "primary=429 | "
                "switching_to=secondary"
            )

            return await self.secondary.responses.create(
                **kwargs
            )

    @asynccontextmanager
    async def stream(self, **kwargs):
        """
        Used for SSE / real-time LLM streaming.

        Failover happens if the primary returns 429
        while opening the stream.

        Once a stream has started, we do not replay
        it on another deployment. That prevents
        duplicate or conflicting streamed tokens.
        """

        async with AsyncExitStack() as stack:

            try:
                stream = await stack.enter_async_context(
                    self.primary.responses.stream(
                        **kwargs
                    )
                )

            except RateLimitError:
                logger.warning(
                    "FOUNDRY_RATE_LIMIT | "
                    "operation=stream | "
                    "primary=429 | "
                    "switching_to=secondary"
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

        except RateLimitError:
            logger.warning(
                "FOUNDRY_RATE_LIMIT | "
                "operation=chat.completions.create | "
                "primary=429 | "
                "switching_to=secondary"
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
