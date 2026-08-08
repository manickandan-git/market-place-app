from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.tools import get_policy
from app.tools.types import ToolContext


class _FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _fake_session_factory():
    return _FakeSession()


def _fake_chunk(topic: str, version: int, text: str):
    return SimpleNamespace(
        chunk_text=text, document=SimpleNamespace(topic=topic, version=version)
    )


@pytest.fixture
def fake_rag(monkeypatch):
    embed_calls: list[str] = []
    search_calls: list[tuple] = []

    def fake_embed(query: str) -> list[float]:
        embed_calls.append(query)
        return [0.1, 0.2, 0.3]

    async def fake_search_policy(query_embedding, session):
        search_calls.append((query_embedding, session))
        return [
            _fake_chunk("returns", 1, "You may return items within 30 days."),
            _fake_chunk(
                "refunds", 2, "Refunds are issued to your original payment method."
            ),
        ]

    monkeypatch.setattr(get_policy, "embed", fake_embed)
    monkeypatch.setattr(get_policy, "search_policy", fake_search_policy)
    monkeypatch.setattr(get_policy, "SessionFactory", _fake_session_factory)

    return SimpleNamespace(embed_calls=embed_calls, search_calls=search_calls)


@pytest.mark.usefixtures("fake_rag")
async def test_handle_returns_results_shaped_from_matched_chunks():
    result = await get_policy.handle(
        {"query": "how long do I have to return something"},
        ToolContext(request_id=None),
    )

    assert result == {
        "results": [
            {
                "topic": "returns",
                "version": 1,
                "chunk_text": "You may return items within 30 days.",
            },
            {
                "topic": "refunds",
                "version": 2,
                "chunk_text": "Refunds are issued to your original payment method.",
            },
        ]
    }


async def test_handle_embeds_the_query_and_passes_vector_to_search(fake_rag):
    await get_policy.handle(
        {"query": "how long do I have to return something"},
        ToolContext(request_id=None),
    )

    assert fake_rag.embed_calls == ["how long do I have to return something"]
    (query_embedding, session) = fake_rag.search_calls[0]
    assert query_embedding == [0.1, 0.2, 0.3]
    assert isinstance(session, _FakeSession)


async def test_handle_returns_empty_results_when_nothing_matches(monkeypatch):
    async def fake_search_policy(query_embedding, session):
        return []

    monkeypatch.setattr(get_policy, "embed", lambda query: [0.0])
    monkeypatch.setattr(get_policy, "search_policy", fake_search_policy)
    monkeypatch.setattr(get_policy, "SessionFactory", _fake_session_factory)

    result = await get_policy.handle(
        {"query": "unrelated question"}, ToolContext(request_id=None)
    )

    assert result == {"results": []}


async def test_handle_raises_validation_error_when_query_missing():
    with pytest.raises(ValidationError):
        await get_policy.handle({}, ToolContext(request_id=None))


def test_get_policy_tool_spec_metadata():
    spec = get_policy.GET_POLICY

    assert spec.name == "get_policy"
    assert spec.handler is get_policy.handle
    assert spec.input_schema["type"] == "object"
    assert "query" in spec.input_schema["properties"]
    assert spec.input_schema["required"] == ["query"]


def test_get_policy_to_anthropic_tool_shape():
    tool = get_policy.GET_POLICY.to_anthropic_tool()

    assert set(tool.keys()) == {"name", "description", "input_schema"}
    assert tool["name"] == "get_policy"
