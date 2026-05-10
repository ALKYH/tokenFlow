from types import SimpleNamespace

from backend.app.schemas.rag import RagChunkHit
from backend.app.services.routing_service import (
    build_rule_documents,
    match_rule,
    score_rule_candidates,
)


def _rule(
    name: str,
    *,
    category: str = "general",
    channel: str = "dashboard",
    keywords: list[str] | None = None,
    action_config: dict | None = None,
):
    return SimpleNamespace(
        name=name,
        category=category,
        channel=channel,
        matcher_config={"keywords": keywords or []},
        action_config=action_config or {"target": name},
    )


def test_match_rule_returns_hits_and_reason():
    rule = _rule("route-search", keywords=["search", "query"])
    matched, score, reason, hits = match_rule(rule, "please search this query for me")
    assert matched is True
    assert score == 1.0
    assert "Matched keywords" in reason
    assert hits == ["search", "query"]


def test_build_rule_documents_contains_rule_context():
    rules = [_rule("route-search", category="knowledge", channel="api", keywords=["search"])]
    documents = build_rule_documents(rules)
    assert len(documents) == 1
    assert "route-search" in documents[0]["content"]
    assert "knowledge" in documents[0]["content"]
    assert "search" in documents[0]["content"]


def test_score_rule_candidates_blends_lexical_and_vector_scores():
    rules = [
        _rule("route-search", keywords=["search", "query"]),
        _rule("route-chat", keywords=["chat", "assistant"]),
    ]
    rag_hits = [
        RagChunkHit(
            chunk_id=1,
            document_id=1,
            chunk_index=0,
            score=0.9,
            text="semantic match",
            metadata={"rule_name": "route-chat"},
        )
    ]
    candidates = score_rule_candidates(
        text="please search this query",
        rules=rules,
        rag_hits=rag_hits,
        route_kind="manual",
    )

    assert len(candidates) == 2
    assert candidates[0].rule_name == "route-search"
    assert candidates[0].lexical_score > 0
    assert candidates[1].rule_name == "route-chat"
    assert candidates[1].vector_score > 0
    assert candidates[1].source == "vector"
