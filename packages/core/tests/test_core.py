import asyncio

import pytest
from faccoder_core.cache import SemanticCache
from faccoder_core.config import FaccoderConfig
from faccoder_core.jsonx import extract_json
from faccoder_core.llm.fake import FakeChatModel
from faccoder_core.llm.registry import get_chat_model
from faccoder_core.llm.rotation import classify_error, requested_wait
from faccoder_core.observability.pricing import cost_usd
from faccoder_core.observability.usage import BudgetExceededError, UsageCallback, usage_scope
from faccoder_core.retrieval.embeddings import HashEmbedder
from faccoder_core.retrieval.fusion import mmr_select, rrf_fuse
from faccoder_core.sandbox import PathOutsideSandboxError, resolve_inside
from faccoder_core.store.sqlite_store import HybridStore, StoredChunk, fts_query
from faccoder_core.structured import OutOfContractError, call_structured
from pydantic import BaseModel


def test_presets_resolve_every_tier():
    from faccoder_core.llm.presets import PRESETS

    for name in PRESETS:
        cfg = FaccoderConfig(preset=name)
        for tier in ("small", "medium", "large"):
            assert cfg.model_for(tier).model


def test_tier_override_wins_over_preset():
    cfg = FaccoderConfig(preset="all-paid", tiers={"small": {"provider": "ollama", "model": "llama3.1"}})
    assert cfg.model_for("small").provider == "ollama"
    assert cfg.model_for("large").provider == "anthropic"


def test_offline_model_is_deterministic():
    model = get_chat_model("medium", config=FaccoderConfig(preset="offline"), tracing=False)
    assert model.invoke("hello").content == model.invoke("hello").content


def test_extract_json_from_prose_and_fences():
    assert extract_json('Sure! ```json\n{"a": 1}\n``` done') == {"a": 1}
    assert extract_json('result: {"b": [1, 2, "x}"]} trailing') == {"b": [1, 2, "x}"]}
    assert extract_json("no json here") is None


class Verdict(BaseModel):
    decision: str
    score: int


def test_structured_retries_with_error_then_succeeds():
    llm = FakeChatModel(responses=["not json", '{"decision": "go", "score": 8}'])
    verdict = asyncio.run(call_structured("judge", llm=llm, schema=Verdict))
    assert verdict.decision == "go" and llm.calls == 2


def test_structured_raises_named_error():
    llm = FakeChatModel(responses=['{"decision": "go"}'])
    with pytest.raises(OutOfContractError):
        asyncio.run(call_structured("judge", llm=llm, schema=Verdict))


def test_rrf_rewards_documents_found_by_several_searches():
    vector = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
    text = [{"id": "c"}, {"id": "d"}]
    fused = rrf_fuse([vector, text])
    assert fused[0]["id"] == "c" and fused[0]["_hits"] == 2


def test_mmr_prefers_diversity():
    docs = [[1, 0], [0.99, 0.01], [0, 1]]
    picked = mmr_select(docs, [1, 0.2], k=2, lambda_mult=0.3)
    # The two near-duplicates must not both be picked.
    assert picked[0] in (0, 1) and picked[1] == 2


def test_error_classification():
    assert classify_error("429 RESOURCE_EXHAUSTED retry in 7s") == "quota"
    assert requested_wait("retry in 7s", 0) == 8.0
    assert classify_error("503 unavailable") == "transient"
    assert classify_error("invalid api key") == "fatal"


def test_cost_and_budget():
    assert cost_usd("unknown-local-model", 1000, 1000) == 0.0
    assert cost_usd("claude-sonnet-5-5", 1_000_000, 0) > 0
    with usage_scope(owner="t", budget_usd=0.0001) as meter:
        meter.add("claude-opus-5-5", 10_000, 10_000)
        with pytest.raises(BudgetExceededError):
            UsageCallback("claude-opus-5-5").on_llm_start({}, [])


def test_hybrid_store_finds_identifier_parts(tmp_path):
    embedder = HashEmbedder(64)
    store = HybridStore(tmp_path / "idx.sqlite", dimensions=64)
    docs = {
        "1": "class CustomerInvoiceService: computes invoice totals",
        "2": "def parse_config(path): reads yaml",
        "3": "procedure TfrmRental.SaveContract; begin end;",
    }
    store.upsert([StoredChunk(id=k, text=v, embedding=embedder.embed_query(v)) for k, v in docs.items()])
    hits = store.hybrid_search("customer invoice", embedder.embed_query("customer invoice"), k=2)
    assert hits[0]["id"] == "1"
    assert '"customer"' in fts_query("CustomerInvoice")
    store.upsert([StoredChunk(id="1", text="changed text", embedding=embedder.embed_query("changed"))])
    assert store.count() == 3


def test_semantic_cache_skips_negative_answers(tmp_path):
    embedder = HashEmbedder(64)
    cache = SemanticCache(HybridStore(tmp_path / "c.sqlite", dimensions=64), embedder, threshold=0.9)
    assert cache.put("how do I reset my password", "Use the reset link on the login page.")
    assert cache.get("how do I reset my password") == "Use the reset link on the login page."
    assert not cache.put("what is the plan", "Not found in the knowledge base.")


def test_sandbox_blocks_escape(tmp_path):
    (tmp_path / "a.txt").write_text("x")
    assert resolve_inside(tmp_path, "a.txt").name == "a.txt"
    with pytest.raises(PathOutsideSandboxError):
        resolve_inside(tmp_path, "../outside.txt")
