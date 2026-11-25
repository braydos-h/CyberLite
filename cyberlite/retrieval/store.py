"""Dependency-free BM25 retrieval with provenance.

This local index is intentionally simple: it makes the RAG baseline reproducible
without an external vector database or embedding API. A dense retriever can be
added as an ablation without changing the evidence-formatting contract.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in _TOKEN_RE.findall(text)]


@dataclass
class Document:
    id: str
    text: str
    source: str
    license: str = "Unknown"
    url: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("document text is empty")
        if not self.id:
            self.id = hashlib.sha256(f"{self.source}:{self.text}".encode()).hexdigest()[:16]


@dataclass
class RetrievedDocument:
    document: Document
    score: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.document.id,
            "score": round(self.score, 6),
            "source": self.document.source,
            "license": self.document.license,
            "url": self.document.url,
            "text": self.document.text,
            "metadata": self.document.metadata,
        }


class BM25Index:
    def __init__(self, *, k1: float = 1.5, b: float = 0.75) -> None:
        if k1 <= 0:
            raise ValueError("k1 must be positive")
        if not 0 <= b <= 1:
            raise ValueError("b must be in [0, 1]")
        self.k1 = k1
        self.b = b
        self.documents: list[Document] = []
        self._tokens: list[list[str]] = []
        self._df: dict[str, int] = {}
        self._avgdl = 0.0
        self._built = False

    def add(self, document: Document) -> None:
        self.documents.append(document)
        self._built = False

    def extend(self, documents: Iterable[Document]) -> None:
        for document in documents:
            self.add(document)

    def build(self) -> None:
        self._tokens = [tokenize(document.text) for document in self.documents]
        self._df = {}
        for tokens in self._tokens:
            for token in set(tokens):
                self._df[token] = self._df.get(token, 0) + 1
        self._avgdl = (
            sum(len(tokens) for tokens in self._tokens) / len(self._tokens) if self._tokens else 0.0
        )
        self._built = True

    def search(self, query: str, *, top_k: int = 5) -> list[RetrievedDocument]:
        if not self._built:
            self.build()
        if top_k <= 0:
            raise ValueError("top_k must be positive")
        query_tokens = tokenize(query)
        if not query_tokens or not self.documents:
            return []
        scores: list[tuple[int, float]] = []
        total_documents = len(self.documents)
        for index, tokens in enumerate(self._tokens):
            length = len(tokens) or 1
            frequencies: dict[str, int] = {}
            for token in tokens:
                frequencies[token] = frequencies.get(token, 0) + 1
            score = 0.0
            for token in query_tokens:
                frequency = frequencies.get(token, 0)
                if frequency == 0:
                    continue
                df = self._df.get(token, 0)
                idf = math.log(1 + (total_documents - df + 0.5) / (df + 0.5))
                denominator = frequency + self.k1 * (
                    1 - self.b + self.b * length / (self._avgdl or 1)
                )
                score += idf * (frequency * (self.k1 + 1)) / denominator
            if score > 0:
                scores.append((index, score))
        scores.sort(key=lambda item: item[1], reverse=True)
        return [
            RetrievedDocument(document=self.documents[index], score=score)
            for index, score in scores[:top_k]
        ]

    def save(self, directory: str | Path) -> None:
        destination = Path(directory)
        destination.mkdir(parents=True, exist_ok=True)
        with (destination / "documents.jsonl").open("w", encoding="utf-8") as handle:
            for document in self.documents:
                handle.write(json.dumps(asdict(document), ensure_ascii=False) + "\n")
        manifest = {
            "format": "cyberlite-bm25-v1",
            "documents": len(self.documents),
            "k1": self.k1,
            "b": self.b,
        }
        (destination / "index.json").write_text(json.dumps(manifest, indent=2) + "\n")

    @classmethod
    def load(cls, directory: str | Path) -> BM25Index:
        source = Path(directory)
        manifest_path = source / "index.json"
        if not manifest_path.is_file():
            raise FileNotFoundError(f"missing index manifest: {manifest_path}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        index = cls(k1=manifest.get("k1", 1.5), b=manifest.get("b", 0.75))
        with (source / "documents.jsonl").open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                payload = json.loads(line)
                index.add(Document(**payload))
        index.build()
        return index


def chunk_text(text: str, *, max_chars: int = 1200, overlap_chars: int = 150) -> list[str]:
    """Split text on paragraph/sentence boundaries with character overlap."""

    text = text.strip()
    if max_chars < 1:
        raise ValueError("max_chars must be positive")
    if overlap_chars >= max_chars:
        raise ValueError("overlap_chars must be smaller than max_chars")
    if len(text) <= max_chars:
        return [text] if text else []
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        pieces = [paragraph]
        if len(paragraph) > max_chars:
            pieces = []
            sentences = _SENTENCE_SPLIT.split(paragraph)
            buffer = ""
            for sentence in sentences:
                if len(buffer) + len(sentence) + 1 > max_chars and buffer:
                    pieces.append(buffer.strip())
                    buffer = sentence
                else:
                    buffer = f"{buffer} {sentence}".strip()
            if buffer:
                pieces.append(buffer.strip())
        for piece in pieces:
            candidate = f"{current}\n\n{piece}".strip() if current else piece
            if len(candidate) > max_chars and current:
                chunks.append(current)
                tail = current[-overlap_chars:] if overlap_chars else ""
                current = f"{tail}\n\n{piece}".strip()
            else:
                current = candidate
    if current:
        chunks.append(current)
    return chunks


def documents_from_directory(
    directory: str | Path,
    *,
    source: str,
    license: str,
    extensions: tuple[str, ...] = (".md", ".txt", ".rst"),
    max_chars: int = 1200,
    overlap_chars: int = 150,
) -> list[Document]:
    documents: list[Document] = []
    root = Path(directory)
    if not root.is_dir():
        raise FileNotFoundError(f"document directory not found: {root}")
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in extensions:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for position, chunk in enumerate(
            chunk_text(text, max_chars=max_chars, overlap_chars=overlap_chars)
        ):
            documents.append(
                Document(
                    id="",
                    text=chunk,
                    source=source,
                    license=license,
                    metadata={"path": str(path), "chunk": position},
                )
            )
    return documents
