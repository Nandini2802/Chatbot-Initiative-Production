"""
Walkthrough feature-key check: keys match ignoring case, spaces, dashes
and underscores ("DAR Dashboard" == "DARdashboard"), but different key
names never match. Uses the real walkthrough workbook.
"""
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.handlers.walkthrough_handler import WALKTHROUGH_FALLBACK, WalkthroughHandler
from app.services.walkthrough_access_service import (
    WalkthroughEngine,
    compact_feature_key,
    granted_feature_keys,
)

ENGINE = WalkthroughEngine(directory=Path("app/data/walkthrough"))
DAR = "Daily Activity Report"


@pytest.mark.parametrize("key_features", [
    # Workbook: "DARView,DARCreate" (either one is enough).
    "DARView", "dar view", "DarView", "DAR_View", "DAR-View", " DARVIEW ",
    "DARCreate", "dar create", "UDPage,CompareUnit,DARCreate,HowToVideos",
])
def test_dar_allowed_for_spelling_variants(key_features):
    assert ENGINE.permission(DAR, key_features) == (True, "feature_key_verified")


@pytest.mark.parametrize("key_features", [
    None, "", "DarAnalytics", "DAR", "View", "DAR Vi", "DAR Dashboard", "UDPage,CompareUnit",
])
def test_dar_still_denied_without_its_key(key_features):
    assert ENGINE.permission(DAR, key_features) == (False, "feature_key_not_granted")


def test_sales_order_key_spelling_tolerant():
    # Workbook key "SalesOrder".
    name = next(g.name for g in ENGINE.guides.values() if (g.key or "").strip() == "SalesOrder")
    assert ENGINE.permission(name, "SalesOrder")[0] is True
    assert ENGINE.permission(name, "Sales Order")[0] is True
    assert ENGINE.permission(name, "Sales")[0] is False


def test_multi_key_guides_still_need_every_key():
    # e.g. Create Lead -> "LeadTab/LeadAdd": both are required, as before.
    guide = next(g for g in ENGINE.guides.values() if "/" in (g.key or ""))
    keys = [k for k in guide.key.split("/") if k.strip()]
    assert ENGINE.permission(guide.name, ",".join(keys))[0] is True
    assert ENGINE.permission(guide.name, keys[0])[0] is False


def test_every_guide_allowed_with_its_exact_workbook_key():
    """Regression: no guide loses access with the keys exactly as in the workbook."""
    checked = 0
    for guide in ENGINE.guides.values():
        if not guide.key:
            continue
        exact = ",".join(k.strip() for k in guide.key.replace("|", "/").replace(",", "/").split("/") if k.strip())
        assert ENGINE.permission(guide.name, exact)[0] is True, guide.name
        assert ENGINE.permission(guide.name, None)[0] is False, guide.name
        checked += 1
    assert checked >= 15


def test_unknown_and_keyless_guides_unchanged():
    assert ENGINE.permission("Not a feature", "DARdashboard") == (False, "unknown_feature")


def test_compaction_helpers():
    assert compact_feature_key("DAR Dashboard") == "dardashboard"
    assert compact_feature_key("DAR_Dashboard") == "dardashboard"
    assert granted_feature_keys("UDPage, DAR Dashboard ,,") == {"udpage", "dardashboard"}
    assert granted_feature_keys(None) == set()


@pytest.mark.asyncio
async def test_denial_log_shows_required_and_granted(caplog):
    handler = WalkthroughHandler(
        engine=ENGINE, key_features="UDPage,DarAnalytics", role="RM", redis_client=None,
    )
    # "Create Lead" needs LeadTab/LeadAdd, which this user does not have.
    with caplog.at_level(logging.INFO, logger="app.handlers.walkthrough_handler"):
        result = await handler.handle(SimpleNamespace(feature_name="Create Lead"))

    # Honest denial (the feature exists, the user has no access).
    assert result.messages == [
        "You don't currently have access to Create Lead in your account."]
    line = next(r.getMessage() for r in caplog.records if "WALKTHROUGH_ACCESS_DENIED" in r.getMessage())
    assert "reason=feature_key_not_granted" in line
    assert "required=['leadtab', 'leadadd']" in line
    assert "granted=['daranalytics', 'udpage']" in line
