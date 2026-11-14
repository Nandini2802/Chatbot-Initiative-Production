
import pytest
import httpx

from types import SimpleNamespace
from unittest.mock import AsyncMock

from openai import RateLimitError

from app.core.foundry_failover import FoundryFailoverClient


def make_429_error():
    request = httpx.Request(
        "POST",
        "https://primary.example.com/responses",
    )

    response = httpx.Response(
        status_code=429,
        request=request,
    )

    return RateLimitError(
        "Too many requests",
        response=response,
        body=None,
    )


@pytest.mark.asyncio
async def test_primary_success():

    primary_parse = AsyncMock(
        return_value="primary_response"
    )

    secondary_parse = AsyncMock()

    primary = SimpleNamespace(
        responses=SimpleNamespace(
            parse=primary_parse
        ),
        close=AsyncMock(),
    )

    secondary = SimpleNamespace(
        responses=SimpleNamespace(
            parse=secondary_parse
        ),
        close=AsyncMock(),
    )

    client = FoundryFailoverClient(
        primary=primary,
        secondary=secondary,
    )

    result = await client.responses.parse(
        model="gpt-5.4",
        input="hello",
    )

    assert result == "primary_response"

    primary_parse.assert_awaited_once()
    secondary_parse.assert_not_awaited()


@pytest.mark.asyncio
async def test_primary_429_uses_secondary():

    primary_parse = AsyncMock(
        side_effect=make_429_error()
    )

    secondary_parse = AsyncMock(
        return_value="secondary_response"
    )

    primary = SimpleNamespace(
        responses=SimpleNamespace(
            parse=primary_parse
        ),
        close=AsyncMock(),
    )

    secondary = SimpleNamespace(
        responses=SimpleNamespace(
            parse=secondary_parse
        ),
        close=AsyncMock(),
    )

    client = FoundryFailoverClient(
        primary=primary,
        secondary=secondary,
    )

    result = await client.responses.parse(
        model="gpt-5.4",
        input="hello",
    )

    assert result == "secondary_response"

    primary_parse.assert_awaited_once()
    secondary_parse.assert_awaited_once_with(
        model="gpt-5.4",
        input="hello",
    )
