import asyncio

from app.database import SessionFactory
from app.models.policy import PolicyChunk, PolicyDocument
from app.rag.chunking import chunk_policies
from app.rag.embeddings import embed_many


async def seed_policies() -> None:
    chunked = chunk_policies()
    async with SessionFactory() as session:
        await session.execute(PolicyChunk.__table__.delete())
        await session.execute(PolicyDocument.__table__.delete())

        for topic, chunks in chunked.items():
            document = PolicyDocument(topic=topic, version=1, body="\n\n".join(chunks))
            session.add(document)
            await session.flush()  # need document.id before creating chunks

            for index, (text, vector) in enumerate(
                zip(chunks, embed_many(chunks), strict=True)
            ):
                session.add(
                    PolicyChunk(
                        document_id=document.id,
                        chunk_index=index,
                        chunk_text=text,
                        embedding=vector,
                    )
                )

        await session.commit()
    print(f"Seeded {len(chunked)} policy documents.")


if __name__ == "__main__":
    asyncio.run(seed_policies())