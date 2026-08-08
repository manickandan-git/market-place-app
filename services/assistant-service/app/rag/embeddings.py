"""Local sentence-transformers embeddings, lazily loaded on first use."""

from functools import lru_cache

from sentence_transformers import SentenceTransformer

from app.config import get_settings

EMBEDDING_DIMENSION = 384


@lru_cache
def _get_model() -> SentenceTransformer:
    model_name = get_settings().embedding_model_name
    model = SentenceTransformer(model_name)
    actual_dim = model.get_embedding_dimension()
    if actual_dim != EMBEDDING_DIMENSION:
        raise ValueError(
            f"embedding_model_name={model_name!r} produces {actual_dim}-dim "
            f"vectors, but PolicyChunk.embedding is fixed at "
            f"{EMBEDDING_DIMENSION} (see app/models/policy.py migration)"
        )
    return model


def embed(text: str) -> list[float]:
    model = _get_model()
    return model.encode(text, normalize_embeddings=True).tolist()


def embed_many(texts: list[str]) -> list[list[float]]:
    model = _get_model()
    return model.encode(texts, normalize_embeddings=True).tolist()
