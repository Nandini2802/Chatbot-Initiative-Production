"""User/session scoped pending project decisions, never project permissions."""
import json


class ProjectSelectionState:
    TTL_SECONDS = 1800

    def __init__(self, redis_client):
        self.redis = redis_client

    @staticmethod
    def key(user_id: str, session_id: str) -> str:
        return f"danube:project-selection:pending:{user_id}:{session_id}"

    async def save(
        self,
        *,
        user_id: str,
        session_id: str,
        original_message: str,
        candidates: list[str],
        intent_type: str,
        routing_result: dict,
        intent_index: int,
        slot: str = "project_name",
        slot_index: int | None = None,
        phase: str = "choose_project",
        selected_projects: list[str] | None = None,
        queue_position: int = 0,
    ):
        if not 2 <= len(candidates) <= 20:
            raise ValueError("Invalid project candidate count")
        if slot not in {"project_name", "compare_project_names"}:
            raise ValueError("Invalid project selection slot")
        data = {
            "version": 2,
            "original_message": original_message,
            "candidates": candidates,
            "intent_type": intent_type,
            "routing_result": routing_result,
            "intent_index": intent_index,
            "slot": slot,
            "slot_index": slot_index,
            "phase": phase,
            "selected_projects": selected_projects or [],
            "queue_position": queue_position,
        }
        serialized = json.dumps(data, ensure_ascii=False)
        if len(serialized) > 40000:
            raise ValueError("Project selection state too large")
        await self.redis.set(self.key(user_id, session_id), serialized, ex=self.TTL_SECONDS)

    async def load(self, *, user_id: str, session_id: str) -> dict | None:
        raw = await self.redis.get(self.key(user_id, session_id))
        if not raw:
            return None
        try:
            data = json.loads(raw)
            intents = data["routing_result"]["intents"]
            valid = (
                isinstance(data, dict)
                and data.get("version") == 2
                and isinstance(data.get("original_message"), str)
                and 0 < len(data["original_message"]) <= 4000
                and isinstance(data.get("intent_type"), str)
                and isinstance(data.get("routing_result"), dict)
                and isinstance(intents, list)
                and 1 <= len(intents) <= 10
                and type(data.get("intent_index")) is int
                and 0 <= data["intent_index"] < len(intents)
                and data.get("slot") in {"project_name", "compare_project_names"}
                and data.get("phase", "choose_project") in {"choose_project", "availability_parameters", "multi_queue"}
                and type(data.get("queue_position", 0)) is int
                and isinstance(data.get("selected_projects", []), list)
                and (data.get("slot_index") is None or type(data["slot_index"]) is int)
                and isinstance(data.get("candidates"), list)
                and 2 <= len(data["candidates"]) <= 20
                and all(
                    isinstance(name, str) and 0 < len(name) <= 200
                    for name in data["candidates"]
                )
            )
            return data if valid else None
        except (TypeError, KeyError, ValueError, IndexError):
            return None

    async def clear(self, *, user_id: str, session_id: str):
        await self.redis.delete(self.key(user_id, session_id))
