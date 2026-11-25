"""Benchmark registry: metadata, licenses, and access status.

CyberLite does not redistribute benchmark datasets. Licenses differ, and some
benchmarks are gated or non-commercial. Adapters accept locally obtained data
after the user has accepted the upstream terms.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class BenchmarkSpec:
    key: str
    title: str
    homepage: str
    paper: str
    license: str
    redistribution: str
    access: str
    notes: str
    fields: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["fields"] = list(self.fields)
        return payload


BENCHMARKS: dict[str, BenchmarkSpec] = {
    "cyberseceval": BenchmarkSpec(
        key="cyberseceval",
        title="CyberSecEval / CyberSecEval 2",
        homepage="https://github.com/meta-llama/PurpleLlama",
        paper="https://arxiv.org/abs/2312.04724",
        license="Llama-3.2-Community (upstream terms; verify current release)",
        redistribution="not permitted by CyberLite; obtain from upstream",
        access="license-gated upstream repository",
        notes=(
            "Use the secure-coding and vulnerability tasks that match the research question. "
            "Do not mix CyberSecEval test items into training data. Report the upstream "
            "version/commit and any subset selection."
        ),
        fields=("id", "task", "prompt", "reference"),
    ),
    "seceval": BenchmarkSpec(
        key="seceval",
        title="SecEval",
        homepage="https://xuanwuai.github.io/SecEval",
        paper="https://xuanwuai.github.io/SecEval",
        license="CC-BY-NC-SA (evaluation-only; non-commercial)",
        redistribution="not permitted by CyberLite; obtain from upstream",
        access="public download after accepting upstream license",
        notes=(
            "Multiple-choice cybersecurity knowledge benchmark. Non-commercial license: do "
            "not use its items for training. Report the date/version downloaded and the "
            "prompt/answer parsing protocol."
        ),
        fields=("id", "question", "choices", "answer"),
    ),
    "heldout": BenchmarkSpec(
        key="heldout",
        title="CyberLite held-out tasks",
        homepage="data/evaluation",
        paper="",
        license="Synthetic / project-curated (see DATASET_CARD.md)",
        redistribution="project-authored smoke items only; no external benchmark items",
        access="local",
        notes=(
            "Independent, project-authored evaluation items kept out of training. The bundled "
            "smoke_eval.jsonl is for pipeline validation, not for scientific claims."
        ),
        fields=("id", "task", "source"),
    ),
}


def list_benchmarks() -> list[dict[str, Any]]:
    return [spec.to_dict() for spec in BENCHMARKS.values()]


def get_benchmark(key: str) -> BenchmarkSpec:
    if key not in BENCHMARKS:
        raise KeyError(f"unknown benchmark {key!r}; known: {', '.join(BENCHMARKS)}")
    return BENCHMARKS[key]


def check_local_benchmark(key: str, path: str) -> dict[str, Any]:
    """Report whether a local benchmark file exists without reading its contents."""

    from pathlib import Path

    spec = get_benchmark(key)
    file_path = Path(path)
    return {
        "benchmark": spec.to_dict(),
        "path": str(file_path),
        "exists": file_path.is_file(),
        "note": (
            "CyberLite does not download or redistribute this benchmark. Confirm that your use "
            "complies with the upstream license."
        ),
    }
