from fastapi import APIRouter, Header, HTTPException, Request

from app.agent.loop import run_agent_loop
from app.tools.types import ToolContext

router = APIRouter()

@router.post("/chat")
async def chat_endpoint(request: Request, authorization: str | None = Header(None)):
    # 1. Parse payload
    try:
        body = await request.json()
        messages = body.get("messages", [])
    except Exception as err:
        raise HTTPException(status_code=400, detail="Invalid JSON body.") from err

    if not messages:
        raise HTTPException(status_code=400, detail="The 'messages' field is required.")

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
    updated_history = await run_agent_loop(messages=messages, context=context)

    # Extract the plain-text reply from the final assistant turn's content
    # blocks, rather than returning the raw block objects to the caller.
    final_assistant_message = updated_history[-1]
    reply = next(
        (
            block.text
            for block in final_assistant_message.get("content", [])
            if getattr(block, "type", None) == "text"
        ),
        "",
    )
    return {"response": reply}
