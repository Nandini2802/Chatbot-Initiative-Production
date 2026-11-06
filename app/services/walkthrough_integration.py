
"""Excel walkthrough integration using request feature keys."""

from typing import Optional

from app.services.walkthrough_access_service import (
    WalkthroughEngine,
)


WALKTHROUGH_FALLBACK = (
    "Great question! While we don't offer that feature yet, "
    "I'd love to help you explore other features which are "
    "available for you."
)


def resolve_walkthrough(
    engine: WalkthroughEngine,
    feature_name: Optional[str],
    key_features: str | None,
) -> dict:

    if not feature_name:
        return {
            "status": "clarification",
            "message": (
                "Which Danube One feature would "
                "you like help with?"
            ),
        }

    result = engine.lookup(
        feature=feature_name,
        key_features=key_features,
    )

    if result["status"] != "ok":
        return {
            "status": "denied",
            "message": WALKTHROUGH_FALLBACK,
        }

    return {
        "status": "ok",
        "feature": result["feature"],
        "steps": result["steps"],
    }
