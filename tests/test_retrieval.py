from __future__ import annotations

from pathlib import Path

import pytest
from cyberlite.retrieval.rag import RAGPipeline
from cyberlite.retrieval.store import (
    BM25Index,
    Document,
    chunk_text,
    documents_from_directory,
)


def _index() -> BM25Index:
    index = BM25Index()
    index.extend(
        [
            Document(
                id="ssh",
                text="Disable SSH password authentication and restrict allowed users.",
                source="synthetic",
                license="Synthetic",
            ),
            Document(
                id="sql",
                text="Use parameterized SQL queries to prevent injection.",
                source="synthetic",
                license="Synthetic",
            ),
            Document(
                id="tls",
                text="Prefer TLS 1.2 and TLS 1.3 and monitor certificate expiry.",
                source="synthetic",
                license="Synthetic",
            ),
        ]
    )
    index.build()
    return index


def test_bm25_ranks_relevant_document_first() -> None:
    results = _index().search("SQL injection parameterized", top_k=2)
    assert [result.document.id for result in results] == ["sql"]
    assert results[0].score > 0


def test_bm25_empty_query_and_unknown_term() -> None:
    index = _index()
    assert index.search("") == []
    assert index.search("kubernetes") == []


def test_bm25_save_load_roundtrip(tmp_path: Path) -> None:
    index = _index()
    index.save(tmp_path / "index")
    loaded = BM25Index.load(tmp_path / "index")
    assert len(loaded.documents) == 3
    assert loaded.search("certificate", top_k=1)[0].document.id == "tls"


def test_chunk_text_respects_size_and_overlap() -> None:
    text = "\n\n".join(["A sentence about network security."] * 100)
    chunks = chunk_text(text, max_chars=200, overlap_chars=20)
    assert len(chunks) > 1
    assert all(len(chunk) <= 230 for chunk in chunks)


def test_chunk_rejects_bad_overlap() -> None:
    with pytest.raises(ValueError):
        chunk_text("text", max_chars=10, overlap_chars=20)


def test_documents_from_directory(tmp_path: Path) -> None:
    (tmp_path / "doc.md").write_text("# SSH\n\nRestrict users.\n\n## TLS\n\nUse modern TLS.")
    documents = documents_from_directory(
        tmp_path, source="docs", license="Synthetic", max_chars=100, overlap_chars=10
    )
    assert documents
    assert all(document.source == "docs" for document in documents)
    assert {document.metadata["path"] for document in documents}


def test_rag_context_has_citations_and_untrusted_warning() -> None:
    pipeline = RAGPipeline(_index())
    messages, sources = pipeline.build_messages("How do I prevent SQL injection?", top_k=2)
    assert sources[0]["citation"] == "S1"
    assert "[S1]" in messages[1]["content"]
    assert "untrusted" in messages[0]["content"].lower()


class _FakeEngine:
    model_id = "fake"

    def chat(self, messages, settings):
        from cyberlite.inference.engine import CompletionResult

        return CompletionResult(
            "Use parameterized queries [S1].", 10, 4, 0.1, 40.0, model_id="fake"
        )


def test_rag_answer_requires_engine_and_cites() -> None:
    pipeline = RAGPipeline(_index())
    with pytest.raises(RuntimeError):
        pipeline.answer("q")
    pipeline.engine = _FakeEngine()
    answer = pipeline.answer("How do I prevent SQL injection?", top_k=2)
    assert "[S1]" in answer.text
    assert answer.retrieved >= 1
    assert answer.metadata["citation_count"] >= 1
