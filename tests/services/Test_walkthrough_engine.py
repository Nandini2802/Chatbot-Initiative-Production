
import pytest

from app.services.walkthrough_access_service import (
    WalkthroughEngine,
)
from app.services.download_availability_access_service import (
    DownloadAvailabilityAccessService,
)
from app.services.feature_access_service import (
    has_key_feature,
    parse_key_features,
)


@pytest.fixture(scope="module")
def engine():
    return WalkthroughEngine(
        directory="app/data/walkthrough"
    )


def test_parse_key_features():
    result = parse_key_features(
        "HomePage, UDPage, CompareUnit"
    )

    assert result == frozenset({
        "homepage",
        "udpage",
        "compareunit",
    })


def test_exact_key_matching():
    assert has_key_feature(
        "HomePage,UDPage,CompareUnit",
        "UDPage",
    )

    assert not has_key_feature(
        "HomePage,SomeUDPageExtra",
        "UDPage",
    )


def test_allowed_walkthrough(engine):
    result = engine.lookup(
        feature="Unit Details Page",
        key_features="HomePage,UDPage,CompareUnit",
    )

    assert result["status"] == "ok"
    assert result["steps"]


def test_denied_walkthrough(engine):
    result = engine.lookup(
        feature="Unit Details Page",
        key_features="HomePage,CompareUnit",
    )

    assert result["status"] == "denied"


def test_missing_feature_keys(engine):
    result = engine.lookup(
        feature="Unit Details Page",
        key_features="",
    )

    assert result["status"] == "denied"


def test_unknown_feature(engine):
    result = engine.lookup(
        feature="Secret Feature",
        key_features="UDPage,CompareUnit",
    )

    assert result["status"] == "denied"


def test_compare_unit_allowed(engine):
    result = engine.lookup(
        feature="Add a Unit to Compare",
        key_features="CompareUnit",
    )

    assert result["status"] == "ok"


def test_download_availability_allowed():
    service = DownloadAvailabilityAccessService()

    allowed, reason = service.check(
        key_features="HomePage,DownloadAvailability"
    )

    assert allowed is True
    assert reason == "feature_key_verified"


def test_download_availability_denied():
    service = DownloadAvailabilityAccessService()

    allowed, reason = service.check(
        key_features="HomePage,CompareUnit"
    )

    assert allowed is False
    assert reason == "download_availability_key_missing"


def test_download_availability_empty_keys():
    service = DownloadAvailabilityAccessService()

    allowed, _ = service.check(
        key_features=""
    )

    assert allowed is False
