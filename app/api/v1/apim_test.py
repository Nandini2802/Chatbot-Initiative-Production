from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class APIMTestRequest(BaseModel):
    user_id: str
    message: str
    start_conversation: bool
    session_id: str | None = None
    role: str
    source: str


@router.post("/apim-test")
async def apim_test(request: APIMTestRequest):
    print(f"Received user_id: {request.user_id}", flush=True)

    return {
        "status": "success",
        "message": "Request reached FastAPI successfully",
        "user_id": request.user_id,
        "service": "Danube Chatbot",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

