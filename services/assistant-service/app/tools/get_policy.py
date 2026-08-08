from pydantic import BaseModel

from app.database import SessionFactory
from app.rag.embeddings import embed
from app.rag.retrieval import search_policy
from app.tools.types import ToolContext, ToolSpec


class GetPolicyArgs(BaseModel):
    query: str


async def handle(args: dict, context: ToolContext) -> dict:
    parsed = GetPolicyArgs.model_validate(args)
    query_embedding = embed(parsed.query)

    async with SessionFactory() as session:
        chunks = await search_policy(query_embedding, session)

    return {
        "results": [
            {
                "topic": chunk.document.topic,
                "version": chunk.document.version,
                "chunk_text": chunk.chunk_text,
            }
            for chunk in chunks
        ]
    }


GET_POLICY = ToolSpec(
    name="get_policy",
    description=(
        "Search the marketplace's return, shipping, and refund policies for "
        "text relevant to a buyer's question. Returns the most relevant policy "
        "excerpts for you to synthesize into an answer — do not quote a result "
        "verbatim if it doesn't fully answer the question, and say you don't "
        "know rather than guessing if nothing relevant comes back."
    ),
    input_schema=GetPolicyArgs.model_json_schema(),
    handler=handle,
)