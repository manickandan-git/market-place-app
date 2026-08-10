import asyncio
from typing import Literal

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from app.agent.loop import run_agent_loop
from app.config import get_settings
from app.tools.types import ToolContext

router = APIRouter()


class ChatMessageIn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class ChatRequest(BaseModel):
    messages: list[ChatMessageIn] = Field(min_length=1, max_length=40)


@router.post("/chat")
async def chat_endpoint(
    body: ChatRequest, request: Request, authorization: str | None = Header(None)
):
    messages = [m.model_dump() for m in body.messages]

    # 2. Extract Bearer token safely (unverified)
    access_token = None
    if authorization and authorization.lower().startswith("bearer "):
        parts = authorization.split(" ", 1)
        if len(parts) == 2:
            access_token = parts[1]

    # 3. Extract request_id injected by CorrelationIdMiddleware
    request_id = getattr(request.state, "request_id", "unknown-id")

    # 4. Build context
    context = ToolContext(request_id=request_id, access_token=access_token)

    # 5. Run the decoupled agent loop
    # Note: messages list is mutated in-place and returned with all turns included
    try:
        updated_history = await asyncio.wait_for(
        run_agent_loop(messages=messages, context=context),
        timeout=get_settings().chat_request_timeout_seconds,
    )
    except TimeoutError:
        raise HTTPException(
        status_code=504,
        detail="The assistant took too long to respond. Please try again.",
    ) from None

    # Extract the plain-text reply from the final assistant turn's content
    # blocks, rather than returning the raw block objects to the caller.
    final_assistant_message = updated_history[-1]
    reply = next(
        (
            block.text
            for block in final_assistant_message.get("content", [])
            if block.type == "text"
        ),
        "",
    )
    return {"response": reply}
