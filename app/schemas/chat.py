from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict, model_validator


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1)
    message: str = Field(min_length=1, max_length=4000)
    start_conversation: bool
    session_id: UUID | None = None
    source: str = Field(min_length=1,max_length=100,)
    app_source: str = Field(min_length=1,max_length=100)
    role: str = Field(min_length=1,max_length=100,)

    @model_validator(mode="after")
    def validate_session(self):
        if self.start_conversation and self.session_id is not None:
            raise ValueError(
                "session_id must be null for a new conversation"
            )

        if not self.start_conversation and self.session_id is None:
            raise ValueError(
                "session_id is required for an existing conversation"
            )

        return self
    

class ChatResponse(BaseModel):
    response: str
    session_id: UUID
    correlation_id: str