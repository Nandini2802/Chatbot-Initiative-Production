
import json


class ProjectSelectionState:
    TTL_SECONDS = 1800

    def __init__(self, redis_client):
        self.redis = redis_client

    @staticmethod
    def key(user_id: str, session_id: str) -> str:
        return (
            "danube:project-selection:pending:"
            f"{user_id}:{session_id}"
        )

    async def save(
        self,
        *,
        user_id: str,
        session_id: str,
        original_message: str,
        candidates: list[str],
        intent_type: str,
    ):
        if not 2 <= len(candidates) <= 20:
            raise ValueError("Invalid candidate count")

        await self.redis.set(
            self.key(user_id, session_id),
            json.dumps({
                "original_message": original_message,
                "candidates": candidates,
                "intent_type": intent_type,
            }),
            ex=self.TTL_SECONDS,
        )

    async def load(
        self,
        *,
        user_id: str,
        session_id: str,
    ):
        raw = await self.redis.get(
            self.key(user_id, session_id)
        )

        if not raw:
            return None

        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            return None

        if not isinstance(data, dict):
            return None

        message = data.get("original_message")
        candidates = data.get("candidates")
        intent_type = data.get("intent_type")

        if (
            not isinstance(message, str)
            or not message.strip()
            or len(message) > 4000
            or not isinstance(intent_type, str)
            or not isinstance(candidates, list)
            or not 2 <= len(candidates) <= 20
            or any(
                not isinstance(name, str)
                or not name.strip()
                or len(name) > 200
                for name in candidates
            )
        ):
            return None

        return data

    async def clear(
        self,
        *,
        user_id: str,
        session_id: str,
    ):
        await self.redis.delete(
            self.key(user_id, session_id)
        )
