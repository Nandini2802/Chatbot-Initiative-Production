
import json
import re
from typing import Any


PAYMENT_SELECTION_TTL = 1800  # 30 minutes


def payment_selection_key(user_id: str, session_id: str) -> str:
    return f"danube:payment_plan:pending:{user_id}:{session_id}"


async def save_pending_payment_selection(
    redis_client,
    user_id: str,
    session_id: str,
    unit_id: str,
    unit_name: str,
    plans: list[dict],
) -> None:
    """
    Save the list of payment plans awaiting user selection.
    Only IDs and names are stored.
    """
    payload = {
        "type": "payment_plan_selection",
        "unit_id": unit_id,
        "unit_name": unit_name,
        "plans": [
            {
                "id": str(plan["Id"]),
                "name": str(plan["Name"]),
            }
            for plan in plans
            if plan.get("Id") and plan.get("Name")
        ],
    }

    key = payment_selection_key(user_id, str(session_id))

    await redis_client.set(
        key,
        json.dumps(payload),
        ex=PAYMENT_SELECTION_TTL,
    )


async def load_pending_payment_selection(
    redis_client,
    user_id: str,
    session_id: str,
) -> dict[str, Any] | None:
    key = payment_selection_key(user_id, str(session_id))

    raw = await redis_client.get(key)

    if not raw:
        return None

    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")

    try:
        payload = json.loads(raw)
    except (ValueError, TypeError):
        await redis_client.delete(key)
        return None

    if (
        not isinstance(payload, dict)
        or payload.get("type") != "payment_plan_selection"
        or not isinstance(payload.get("plans"), list)
    ):
        await redis_client.delete(key)
        return None

    return payload


async def clear_pending_payment_selection(
    redis_client,
    user_id: str,
    session_id: str,
) -> None:
    await redis_client.delete(
        payment_selection_key(user_id, str(session_id))
    )


def normalize_plan_name(value: str) -> str:
    return " ".join(value.casefold().split())


def match_selected_plan(
    message: str,
    plans: list[dict],
) -> dict | None:
    """
    Match exact plan name or explicit option number.

    Returns None when the selection is absent or ambiguous.
    """
    normalized = normalize_plan_name(message)

    matches = [
        plan
        for plan in plans
        if normalize_plan_name(plan["name"]) == normalized
    ]

    if len(matches) == 1:
        return matches[0]

    numbered = re.fullmatch(
        r"(?:option\s+|plan\s+|number\s+)?(\d+)",
        normalized,
    )

    if numbered:
        index = int(numbered.group(1)) - 1

        if 0 <= index < len(plans):
            return plans[index]

    return None
