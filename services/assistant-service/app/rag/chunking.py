"""
 Split raw policy text into paragraph-level chunks.
"""

from app.rag.policy_content import SEED_POLICIES


def chunk_text(text: str) -> list[str]:
    """Split the input text into paragraph chunks.

    Args:
        text (str): The input text to be chunked.

    Returns:
        list[str]: A list of paragraph chunks.
    """
    # Split the text by double newlines to get paragraphs
    paragraphs = text.split("\n\n")
    # Strip whitespace from each paragraph and filter out empty paragraphs
    chunks = [para.strip() for para in paragraphs if para.strip()]
    return chunks


def chunk_policies(
    policies: dict[str, str] = SEED_POLICIES,
) -> dict[str, list[str]]:
    """Chunk every seed policy document, keyed by topic.

    Shaped for the ingestion script: each topic's chunk list is inserted
    as ordered PolicyChunk rows (list index becomes chunk_index).
    """
    return {topic: chunk_text(body) for topic, body in policies.items()}