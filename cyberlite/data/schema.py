"""Dataset record schema and JSONL I/O.

The canonical interchange format is JSON Lines. A record is one of:

* chat SFT:      ``messages`` (list of ``{role, content}``)
* completion:    ``prompt`` + ``response``
* fill-in-middle: ``prefix`` + ``suffix`` + ``middle``

Every record must carry provenance (``source``, ``license``, optionally ``url``).
Nothing is downloaded implicitly by these utilities.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

RecordKind = Literal["chat", "completion", "fim"]

VALID_ROLES = {"system", "user", "assistant"}


@dataclass
class Record:
    id: str
    source: str
    license: str
    task: str = "knowledge"
    messages: list[dict[str, str]] | None = None
    prompt: str | None = None
    response: str | None = None
    prefix: str | None = None
    suffix: str | None = None
    middle: str | None = None
    url: str = ""
    split: str = "train"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.source = self.source.strip()
        self.license = self.license.strip()
        if not self.source:
            raise ValueError("record.source is required for provenance")
        if not self.license:
            raise ValueError("record.license is required for provenance")
        if not self.id:
            self.id = self.compute_id()
        validate_record(self)

    @property
    def kind(self) -> RecordKind:
        if self.messages:
            return "chat"
        if self.prefix is not None or self.suffix is not None or self.middle is not None:
            return "fim"
        return "completion"

    def compute_id(self) -> str:
        digest = hashlib.sha256()
        digest.update(self.source.encode())
        if self.messages:
            digest.update(json.dumps(self.messages, sort_keys=True).encode())
        for value in (self.prompt, self.response, self.prefix, self.suffix, self.middle):
            if value is not None:
                digest.update(b"\x00")
                digest.update(value.encode())
        return f"{self.source}-{digest.hexdigest()[:16]}"

    def text_for_dedup(self) -> str:
        parts: list[str] = []
        if self.messages:
            parts.extend(message["content"] for message in self.messages)
        for value in (self.prompt, self.response, self.prefix, self.suffix, self.middle):
            if value:
                parts.append(value)
        return "\n".join(parts)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "source": self.source,
            "license": self.license,
            "task": self.task,
            "kind": self.kind,
            "split": self.split,
            "metadata": self.metadata,
        }
        if self.url:
            payload["url"] = self.url
        if self.messages is not None:
            payload["messages"] = self.messages
        for key in ("prompt", "response", "prefix", "suffix", "middle"):
            value = getattr(self, key)
            if value is not None:
                payload[key] = value
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Record:
        if not isinstance(payload, dict):
            raise ValueError("record must be a JSON object")
        allowed = {
            "id",
            "source",
            "license",
            "task",
            "messages",
            "prompt",
            "response",
            "prefix",
            "suffix",
            "middle",
            "url",
            "split",
            "metadata",
            "kind",
        }
        unknown = set(payload) - allowed
        if unknown:
            raise ValueError(f"unknown record fields: {sorted(unknown)}")
        data = {key: value for key, value in payload.items() if key != "kind"}
        data.setdefault("id", "")
        data.setdefault("source", "")
        data.setdefault("license", "")
        return cls(**data)


def validate_record(record: Record) -> None:
    """Validate structural invariants for a record."""

    if record.messages:
        if len(record.messages) < 2:
            raise ValueError("chat record needs at least one user and one assistant message")
        roles: set[str] = set()
        for index, message in enumerate(record.messages):
            if set(message) != {"role", "content"}:
                raise ValueError(f"message {index} must contain exactly role and content")
            if message["role"] not in VALID_ROLES:
                raise ValueError(f"invalid role at message {index}: {message['role']!r}")
            if not isinstance(message["content"], str) or not message["content"].strip():
                raise ValueError(f"empty content at message {index}")
            roles.add(message["role"])
        if "assistant" not in roles:
            raise ValueError("chat record must contain an assistant turn")
        if record.messages[-1]["role"] != "assistant":
            raise ValueError("chat record must end with an assistant turn")
        return

    if record.kind == "fim":
        if record.middle is None:
            raise ValueError("FIM record requires a non-null middle completion")
        if not record.middle.strip():
            raise ValueError("FIM middle completion is empty")
        if record.prefix is None:
            raise ValueError("FIM record requires a prefix (may be empty string)")
        return

    if not record.prompt or not record.response:
        raise ValueError("completion record requires non-empty prompt and response")


def iter_jsonl(path: str | Path) -> Iterator[tuple[int, dict[str, Any]]]:
    """Yield ``(line_number, object)`` pairs with useful error messages."""

    file_path = Path(path)
    with file_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{file_path}:{line_number}: invalid JSON: {exc}") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"{file_path}:{line_number}: expected a JSON object")
            yield line_number, payload


def load_records(path: str | Path, *, strict: bool = True) -> list[Record]:
    """Load and validate records, collecting failures when ``strict=False``."""

    records: list[Record] = []
    errors: list[str] = []
    for line_number, payload in iter_jsonl(path):
        try:
            records.append(Record.from_dict(payload))
        except (TypeError, ValueError) as exc:
            message = f"{path}:{line_number}: {exc}"
            if strict:
                raise ValueError(message) from exc
            errors.append(message)
    if errors:
        # The caller can inspect the count via the exception message, but the
        # valid records are still usable in non-strict mode.
        print(f"warning: skipped {len(errors)} invalid records; first: {errors[0]}")
    return records


def write_jsonl(records: Iterator[Record] | list[Record], path: str | Path) -> int:
    """Atomically write records and return the number written."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    handle = tempfile.NamedTemporaryFile(  # noqa: SIM115 - manual cleanup below
        mode="w", encoding="utf-8", dir=destination.parent, delete=False, suffix=".tmp"
    )
    try:
        with handle:
            for record in records:
                handle.write(json.dumps(record.to_dict(), ensure_ascii=False, sort_keys=True))
                handle.write("\n")
                count += 1
        os.replace(handle.name, destination)
    except BaseException:
        if os.path.exists(handle.name):
            os.unlink(handle.name)
        raise
    return count


def sha256_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def count_by(records: list[Record], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        value = str(getattr(record, key, "unknown"))
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))
