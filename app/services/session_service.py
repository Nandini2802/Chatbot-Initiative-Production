
"""
Session service for Danube Properties Chatbot.

Responsibilities:
- Manage user-owned chat sessions
- Save and retrieve conversation messages
- Maintain session activity timestamps
- Retrieve recent conversation context
- Record query execution details
- Control database transactions
"""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.repositories.session_repo import SessionRepository
from app.persistence.repositories.chat_history_repo import ChatHistoryRepository
from app.persistence.repositories.query_log_repo import QueryLogRepository


class SessionNotFoundError(Exception):
    """Session does not exist or is not accessible to this user."""


class InvalidMessageError(ValueError):
    """Invalid chat message."""


class SessionService:

    def __init__(self, db: AsyncSession):
        self.db = db

        self.session_repo = SessionRepository(db)
        self.history_repo = ChatHistoryRepository(db)
        self.query_log_repo = QueryLogRepository(db)

    @staticmethod
    def _validate_user(user_id: str) -> str:
        if not user_id or not user_id.strip():
            raise ValueError("Authenticated user ID is required")
        return user_id

    async def _require_session(
        self,
        session_id: UUID,
        user_id: str,
    ):
        """
        Retrieve a session owned by the current user.

        Return the same error for nonexistent and
        unauthorized sessions.
        """
        session = await self.session_repo.get_by_id(
            session_id=session_id,
            user_id=user_id,
        )

        if session is None:
            raise SessionNotFoundError(
                "Session not found"
            )

        return session

    async def create_session(
        self,
        user_id: str,
        title: str | None = None,
    ):
        user_id = self._validate_user(user_id)

        session = await self.session_repo.create(
            user_id=user_id,
            title=title,
        )

        await self.db.commit()
        await self.db.refresh(session)

        return session

    async def get_session(
        self,
        session_id: UUID,
        user_id: str,
    ):
        user_id = self._validate_user(user_id)

        return await self._require_session(
            session_id=session_id,
            user_id=user_id,
        )

    async def list_sessions(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
    ):
        user_id = self._validate_user(user_id)

        if not 1 <= limit <= 100:
            raise ValueError("Limit must be between 1 and 100")

        if offset < 0:
            raise ValueError("Offset cannot be negative")

        return await self.session_repo.list_by_user(
            user_id=user_id,
            limit=limit,
            offset=offset,
        )

    async def save_message(
        self,
        session_id: UUID,
        user_id: str,
        role: str,
        content: str,
    ):
        user_id = self._validate_user(user_id)

        if role not in {"user", "assistant"}:
            raise InvalidMessageError(
                "Role must be 'user' or 'assistant'"
            )

        if not content or not content.strip():
            raise InvalidMessageError(
                "Message content cannot be empty"
            )

        session = await self._require_session(
            session_id=session_id,
            user_id=user_id,
        )

        message = await self.history_repo.create(
            session_id=session.id,
            role=role,
            content=content,
        )

        session.updated_at = datetime.now(timezone.utc)

        await self.db.commit()
        await self.db.refresh(message)

        return message

    async def get_history(
        self,
        session_id: UUID,
        user_id: str,
        limit: int = 50,
    ):
        user_id = self._validate_user(user_id)

        if not 1 <= limit <= 200:
            raise ValueError("Limit must be between 1 and 200")

        await self._require_session(
            session_id=session_id,
            user_id=user_id,
        )

        return await self.history_repo.list_by_session(
            session_id=session_id,
            limit=limit,
        )

    async def get_recent_context(
        self,
        session_id: UUID,
        user_id: str,
        message_limit: int = 10,
    ) -> list[dict]:
        """
        Return recent messages in chronological order
        for future LLM context construction.
        """
        messages = await self.get_history(
            session_id=session_id,
            user_id=user_id,
            limit=message_limit,
        )

        return [
            {
                "role": message.role,
                "content": message.content,
            }
            for message in messages
        ]

    async def update_session_title(
        self,
        session_id: UUID,
        user_id: str,
        title: str,
    ):
        user_id = self._validate_user(user_id)

        if not title or not title.strip():
            raise ValueError("Session title cannot be empty")

        if len(title) > 255:
            raise ValueError("Session title is too long")

        session = await self._require_session(
            session_id=session_id,
            user_id=user_id,
        )

        session.title = title.strip()
        session.updated_at = datetime.now(timezone.utc)

        await self.db.commit()
        await self.db.refresh(session)

        return session

    async def delete_session(
        self,
        session_id: UUID,
        user_id: str,
    ) -> None:
        user_id = self._validate_user(user_id)

        await self._require_session(
            session_id=session_id,
            user_id=user_id,
        )

        await self.session_repo.delete(
            session_id=session_id,
            user_id=user_id,
        )

        await self.db.commit()

    async def log_query(
        self,
        session_id: UUID,
        user_id: str,
        query_text: str,
        intent: str | None = None,
        status: str = "pending",
        latency_ms: int | None = None,
    ):
        user_id = self._validate_user(user_id)

        if not query_text or not query_text.strip():
            raise ValueError("Query text cannot be empty")

        if latency_ms is not None and latency_ms < 0:
            raise ValueError("Latency cannot be negative")

        await self._require_session(
            session_id=session_id,
            user_id=user_id,
        )

        log = await self.query_log_repo.create(
            session_id=session_id,
            user_id=user_id,
            query_text=query_text,
            intent=intent,
            status=status,
            latency_ms=latency_ms,
        )

        await self.db.commit()
        await self.db.refresh(log)

        return log
