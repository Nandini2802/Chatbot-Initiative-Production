"""
Walkthrough videos: all videos the user may watch are collected, then the
LLM keeps only the one or two whose titles fit the question.
"""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.handlers.walkthrough_handler import WalkthroughHandler
from app.services import how_to_video_selector as sel
from app.services.how_to_video_selector import VideoSelection, select_relevant_videos
from app.services.how_to_video_service import HowToVideoService
from app.services.walkthrough_access_service import WalkthroughEngine

ENGINE = WalkthroughEngine(directory=Path("app/data/walkthrough"))


def yt(n):
    return f"https://youtu.be/{'abcdefghij'}{n}"


DAR_TITLES = [
    "How to Raise Daily Activity Report (DAR)",
    "How to View DAR Stories",
    "Update MOM Enhancements",
    "How to Create DAR for Customer Meeting",
    "DAR Fifth Video",
]

CACHE = {"data": {"howToVideos": [
    {   # one record with five videos, as in production
        "title": "Daily Activity Report",
        "allowed_roles": ["All"],
        "videos": [
            {"title": t, "video_url": yt(i), "video_duration": "01:00"}
            for i, t in enumerate(DAR_TITLES)
        ],
    },
    {
        "title": "How to change password",
        "allowed_roles": ["All"],
        "videos": [{"title": "How to change password", "video_url": yt(5)}],
    },
    {
        "title": "How to view sales order",
        "allowed_roles": ["Agency Admin"],          # not for RM
        "videos": [{"title": "Sales order", "video_url": yt(6)}],
    },
    {
        "title": "Some record with no rule",       # unknown: fails closed
        "allowed_roles": ["All"],
        "videos": [{"title": "Secret", "video_url": yt(7)}],
    },
    {
        "title": "How to create lead",              # duplicate URL is dropped
        "allowed_roles": ["All"],
        "videos": [{"title": "Dup", "video_url": yt(5)}],
    },
]}}


def video_service():
    redis = AsyncMock()
    redis.get.return_value = json.dumps(CACHE)
    return HowToVideoService(redis)


def titles(videos):
    return [v["title"] for v in videos]


# ---------------------------------------------------------------------------
# Which videos the user may watch
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_permitted_videos_follow_keys_and_roles():
    videos = await video_service().find_permitted_videos(
        key_features="DARCreate,ChangePassword,SalesOrder,LeadTab", role="RM")
    assert titles(videos) == DAR_TITLES + ["How to change password"]
    assert {v["group"] for v in videos} == {"Daily Activity Report", "How to change password"}


@pytest.mark.asyncio
async def test_permitted_videos_role_allowed():
    videos = await video_service().find_permitted_videos(
        key_features="SalesOrder", role="Agency Admin")
    assert titles(videos) == ["Sales order"]


@pytest.mark.asyncio
@pytest.mark.parametrize("keys", ["DARView", "dar_view", "DAR Create"])
async def test_permitted_videos_key_spelling_tolerant(keys):
    videos = await video_service().find_permitted_videos(key_features=keys, role="RM")
    assert titles(videos) == DAR_TITLES


@pytest.mark.asyncio
@pytest.mark.parametrize("keys,role", [("", "RM"), (None, "RM"), ("DARCreate", ""), ("UDPage", "RM")])
async def test_permitted_videos_empty_without_access(keys, role):
    assert await video_service().find_permitted_videos(key_features=keys, role=role) == []


# ---------------------------------------------------------------------------
# The LLM selector
# ---------------------------------------------------------------------------

def fake_client(ids=None, error=None, delay=0.0):
    calls = []

    async def parse(**kwargs):
        calls.append(kwargs)
        if delay:
            await asyncio.sleep(delay)
        if error:
            raise error
        return SimpleNamespace(output_parsed=VideoSelection(selected_ids=ids or []))

    client = SimpleNamespace(responses=SimpleNamespace(parse=parse))
    return client, calls


VIDEOS = [{"title": t, "group": "Daily Activity Report", "player_url": yt(i)}
          for i, t in enumerate(DAR_TITLES)]


async def select(client, videos=VIDEOS, question="How to use dar"):
    return await select_relevant_videos(
        question=question, feature_name="Daily Activity Report",
        videos=videos, client=client, model="m")


@pytest.mark.asyncio
async def test_selector_returns_only_chosen_video():
    client, calls = fake_client([1])
    assert titles(await select(client)) == ["How to Raise Daily Activity Report (DAR)"]
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_selector_sends_only_question_feature_and_titles():
    client, calls = fake_client([1])
    await select(client)
    payload = json.loads(calls[0]["input"][0]["content"])
    assert payload["user_question"] == "How to use dar"
    assert payload["walkthrough"] == "Daily Activity Report"
    assert payload["videos"][0] == {
        "id": 1, "title": DAR_TITLES[0], "group": "Daily Activity Report"}
    assert "youtu" not in calls[0]["input"][0]["content"]     # no links sent


@pytest.mark.asyncio
async def test_selector_keeps_order_and_caps_at_two():
    client, _ = fake_client([4, 1, 2])
    assert titles(await select(client)) == [DAR_TITLES[3], DAR_TITLES[0]]


@pytest.mark.asyncio
@pytest.mark.parametrize("ids", [[0], [99], [-1]])
async def test_selector_ignores_ids_outside_the_list(ids):
    client, _ = fake_client(ids)
    assert await select(client) == []


@pytest.mark.asyncio
async def test_selector_repeated_id_shows_video_once():
    client, _ = fake_client([1, 1])
    assert await select(client) == [VIDEOS[0]]


@pytest.mark.asyncio
async def test_selector_empty_choice_shows_nothing():
    client, _ = fake_client([])
    assert await select(client) == []


@pytest.mark.asyncio
async def test_selector_failure_shows_nothing():
    client, _ = fake_client(error=RuntimeError("down"))
    assert await select(client) == []


@pytest.mark.asyncio
async def test_selector_timeout_shows_nothing(monkeypatch):
    monkeypatch.setattr(sel, "SELECTION_TIMEOUT_SECONDS", 0.05)
    client, _ = fake_client([1], delay=1)
    assert await select(client) == []


@pytest.mark.asyncio
async def test_selector_no_videos_or_no_client_makes_no_call():
    client, calls = fake_client([1])
    assert await select(client, videos=[]) == []
    assert await select(None) == []
    assert calls == []


# ---------------------------------------------------------------------------
# Handler end to end
# ---------------------------------------------------------------------------

async def run_handler(message, client, keys="DARCreate,ChangePassword"):
    h = WalkthroughHandler(engine=ENGINE, key_features=keys, role="RM",
                           redis_client=None, message=message,
                           llm_client=client, llm_model="m")
    h.video_service = video_service()
    return await h.handle(SimpleNamespace(feature_name=None))


@pytest.mark.asyncio
async def test_how_to_use_dar_shows_one_video():
    client, calls = fake_client([1])
    result = await run_handler("How to use dar", client)

    assert result.generation_context["feature_name"] == "Daily Activity Report"
    assert len(result.html_blocks) == 1
    html = result.html_blocks[0]["html"]
    assert DAR_TITLES[0] in html
    for other in DAR_TITLES[1:] + ["How to change password"]:
        assert other not in html
    # The LLM saw every permitted video (5 DAR + change password).
    assert len(json.loads(calls[0]["input"][0]["content"])["videos"]) == 6


@pytest.mark.asyncio
async def test_steps_still_sent_when_llm_fails():
    client, _ = fake_client(error=RuntimeError("down"))
    result = await run_handler("How to use dar", client)
    assert result.generation_context["approved_steps"].startswith("Step 1")
    assert "Step 3" in result.generation_context["approved_steps"]
    assert result.html_blocks == []


@pytest.mark.asyncio
async def test_no_video_when_llm_finds_none_relevant():
    client, _ = fake_client([])
    result = await run_handler("How to use dar", client)
    assert result.html_blocks == []
    assert result.generation_context["feature_name"] == "Daily Activity Report"
