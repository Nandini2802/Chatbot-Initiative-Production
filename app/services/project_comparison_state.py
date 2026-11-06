
import json


class ProjectComparisonState:
    """Pending project comparisons, scoped to user and session."""

    TTL_SECONDS = 1800

    def __init__(self, redis_client):
        self.redis = redis_client

    @staticmethod
    def key(user_id: str, session_id: str) -> str:
        return (
            "danube:project-comparison:pending:"
            f"{user_id}:{session_id}"
        )

    async def save(
        self,
        *,
        user_id: str,
        session_id: str,
        references: list[str],
    ):
        if len(references) != 2:
            raise ValueError("Exactly two references are required")

        await self.redis.set(
            self.key(user_id, session_id),
            json.dumps({"references": references}),
            ex=self.TTL_SECONDS,
        )

    async def load(self, *, user_id: str, session_id: str):
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

        refs = data.get("references")
        if (
            not isinstance(refs, list)
            or len(refs) != 2
            or any(
                not isinstance(value, str)
                or not value.strip()
                or len(value) > 200
                for value in refs
            )
        ):
            return None

        return data

    async def clear(self, *, user_id: str, session_id: str):
        await self.redis.delete(
            self.key(user_id, session_id)
        )
