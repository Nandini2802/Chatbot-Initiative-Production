
import json


class UnitComparisonState:
    """Store an unfinished comparison per authenticated user/session."""

    TTL_SECONDS = 1800  # 30 minutes

    def __init__(self, redis_client):
        self.redis = redis_client

    @staticmethod
    def key(user_id: str, session_id: str) -> str:
        return (
            f"danube:unit-comparison:pending:"
            f"{user_id}:{session_id}"
        )

    async def save(self, *, user_id, session_id, unit_ids):
        await self.redis.set(
            self.key(user_id, session_id),
            json.dumps({"unit_ids": [str(uid) for uid in unit_ids]}),
            ex=self.TTL_SECONDS,
        )

    async def load(self, *, user_id, session_id):
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

        unit_ids = data.get("unit_ids")

        if (
            not isinstance(unit_ids, list)
            or len(unit_ids) > 2
            or any(not isinstance(uid, str) for uid in unit_ids)
        ):
            return None

        return data

    async def clear(self, *, user_id, session_id):
        await self.redis.delete(
            self.key(user_id, session_id)
        )
