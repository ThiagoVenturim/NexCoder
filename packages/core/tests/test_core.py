import asyncio

import pytest
from nexcoder_core.cache import SemanticCache
from nexcoder_core.config import NexcoderConfig
from nexcoder_core.jsonx import extract_json
from nexcoder_core.llm.fake import FakeChatModel
from nexcoder_core.llm.registry import get_chat_model
from nexcoder_core.llm.rotation import classify_error, requested_wait
from nexcoder_core.observability.pricing import cost_usd
from nexcoder_core.observability.usage import BudgetExceededError, UsageCallback, usage_scope
from nexcoder_core.retrieval.embeddings import HashEmbedder
from nexcoder_core.retrieval.fusion import mmr_select, rrf_fuse
from nexcoder_core.sandbox import PathOutsideSandboxError, resolve_inside
from nexcoder_core.store.sqlite_store import HybridStore, StoredChunk, fts_query
from nexcoder_core.structured import OutOfContractError, call_structured
from pydantic import BaseModel


def test_presets_resolve_every_tier():
    from nexcoder_core.llm.presets import PRESETS

    for name in PRESETS:
        cfg = NexcoderConfig(preset=name)
        for tier in ("small", "medium", "large"):
            assert cfg.model_for(tier).model


def test_tier_override_wins_over_preset():
    cfg = NexcoderConfig(preset="all-paid", tiers={"small": {"provider": "ollama", "model": "llama3.1"}})
    assert cfg.model_for("small").provider == "ollama"
    assert cfg.model_for("large").provider == "anthropic"


def test_offline_model_is_deterministic():
    model = get_chat_model("medium", config=NexcoderConfig(preset="offline"), tracing=False)
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


def test_hybrid_store_where_filter_and_metadata_helpers(tmp_path):
    embedder = HashEmbedder(64)
    store = HybridStore(tmp_path / "where.sqlite", dimensions=64)
    c1 = StoredChunk(
        id="c1",
        text="def calculate_vat(): return 0.2",
        metadata={"lang": "python", "file_path": "tax/vat.py"},
        embedding=embedder.embed_query("calculate vat"),
    )
    c2 = StoredChunk(
        id="c2",
        text="function CalculateVAT: Double; begin Result := 0.2; end;",
        metadata={"lang": "delphi", "file_path": "tax/vat.pas"},
        embedding=embedder.embed_query("calculate vat"),
    )
    c3 = StoredChunk(
        id="c3",
        text="def calculate_income_tax(): return 0.15",
        metadata={"lang": "python", "file_path": "tax/income.py"},
        embedding=embedder.embed_query("calculate income tax"),
    )
    store.upsert([c1, c2, c3])

    # text_search with where filter
    py_text_hits = store.text_search("calculate", where={"lang": "python"})
    assert len(py_text_hits) == 2
    assert all(h["metadata"]["lang"] == "python" for h in py_text_hits)

    delphi_text_hits = store.text_search("calculate", where={"lang": "delphi"})
    assert len(delphi_text_hits) == 1
    assert delphi_text_hits[0]["id"] == "c2"

    # vector_search with where filter
    py_vec_hits = store.vector_search(embedder.embed_query("calculate vat"), k=10, where={"lang": "python"})
    assert len(py_vec_hits) == 2
    assert all(h["metadata"]["lang"] == "python" for h in py_vec_hits)

    # hybrid_search with where filter
    delphi_hybrid_hits = store.hybrid_search("calculate", embedder.embed_query("calculate"), where={"lang": "delphi"})
    assert len(delphi_hybrid_hits) == 1
    assert delphi_hybrid_hits[0]["id"] == "c2"

    # get_embeddings
    embs = store.get_embeddings(["c1", "c2", "nonexistent"])
    assert "c1" in embs and "c2" in embs
    assert "nonexistent" not in embs
    assert len(embs["c1"]) == 64

    # get_metadata_values
    file_map = store.get_metadata_values("file_path")
    assert file_map == {"c1": "tax/vat.py", "c2": "tax/vat.pas", "c3": "tax/income.py"}

    # delete_by_metadata
    deleted = store.delete_by_metadata("file_path", "tax/vat.pas")
    assert deleted == 1
    assert store.get("c2") is None
    assert store.count() == 2


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
