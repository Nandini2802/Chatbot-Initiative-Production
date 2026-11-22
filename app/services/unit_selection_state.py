
import json


class UnitSelectionState:
    TTL_SECONDS = 1800

    def __init__(self, redis_client):
        self.redis = redis_client

    @staticmethod
    def key(user_id, session_id):
        return (
            "danube:shared-unit-selection:"
            f"{user_id}:{session_id}"
        )

    async def save(
        self,
        *,
        user_id,
        session_id,
        routing_result,
        intent_index,
        slot_index,
        candidate_ids,
        reference,
    ):
        payload = {
            "routing_result": routing_result,
            "intent_index": intent_index,
            "slot_index": slot_index,
            "candidate_ids": [
                str(value) for value in candidate_ids
            ],
            "reference": reference,
        }

        await self.redis.set(
            self.key(user_id, session_id),
            json.dumps(payload),
            ex=self.TTL_SECONDS,
        )

    async def load(self, *, user_id, session_id):
        raw = await self.redis.get(
            self.key(user_id, session_id)
        )

        if not raw:
            return None

        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")

        try:
            payload = json.loads(raw)
        except (ValueError, TypeError):
            await self.clear(
                user_id=user_id,
                session_id=session_id,
            )
            return None

        if not isinstance(payload, dict):
            return None

        return payload

    async def clear(self, *, user_id, session_id):
        await self.redis.delete(
            self.key(user_id, session_id)
        )
