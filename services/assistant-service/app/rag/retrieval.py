from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.policy import PolicyChunk


async def search_policy(
    query_embedding: list[float], session: AsyncSession, k: int = 5
) -> list[PolicyChunk]:
    stmt = (
        select(PolicyChunk)
        .options(selectinload(PolicyChunk.document))
        .order_by(PolicyChunk.embedding.cosine_distance(query_embedding))
        .limit(k)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
