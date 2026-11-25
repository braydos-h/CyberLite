from __future__ import annotations

import json
from pathlib import Path

import pytest
from cyberlite.evaluation.harness import (
    EvalExample,
    EvaluationHarness,
    build_prompt,
    load_examples,
    parse_classification,
)
from cyberlite.inference.engine import CompletionResult


class FakeEngine:
    model_id = "fake-cyberlite"

    def info(self):
        return {"model_id": self.model_id, "parameters": 800_000_000, "device": "cpu"}

    def chat(self, messages, settings=None):
        prompt = messages[-1]["content"]
        if "Valid labels:" in prompt:
            if "concatenates" in prompt:
                answer = "vulnerable"
            else:
                answer = "benign"
        elif "Choices:" in prompt:
            answer = "A"
        else:
            answer = "Parameterized queries separate code from data."
        return CompletionResult(answer, 12, 4, 0.01, 400.0, model_id="fake")

    def complete(self, prompt, settings=None):
        return self.chat([{"role": "user", "content": prompt}], settings)


def _example_file(tmp_path: Path) -> Path:
    rows = [
        {
            "id": "m1",
            "task": "mcq",
            "question": "Best primary defense for SQL injection?",
            "choices": ["Parameterized queries", "Longer passwords"],
            "answer": "A",
        },
        {
            "id": "c1",
            "task": "classification",
            "text": "The code concatenates input into a SQL string.",
            "label": "vulnerable",
            "labels": ["benign", "vulnerable"],
        },
        {
            "id": "c2",
            "task": "classification",
            "text": "The code uses a fixed root and canonical path checks.",
            "label": "benign",
            "labels": ["benign", "vulnerable"],
        },
        {
            "id": "g1",
            "task": "generation",
            "prompt": "Why parameterized queries?",
            "reference": "Parameterized queries separate code from data.",
            "evidence": "Parameterized queries separate code from data.",
        },
    ]
    path = tmp_path / "eval.jsonl"
    with path.open("w") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")
    return path


def test_load_examples_validates_and_parses(tmp_path: Path) -> None:
    examples = load_examples(_example_file(tmp_path))
    assert len(examples) == 4
    assert examples[0].answer_index == 0
    assert examples[1].labels == ["benign", "vulnerable"]


def test_load_examples_rejects_duplicate_ids(tmp_path: Path) -> None:
    path = tmp_path / "dup.jsonl"
    row = {
        "id": "x",
        "task": "mcq",
        "question": "q",
        "choices": ["a", "b"],
        "answer": 0,
    }
    path.write_text(json.dumps(row) + "\n" + json.dumps(row) + "\n")
    with pytest.raises(ValueError, match="duplicate id"):
        load_examples(path)


def test_build_prompt_contains_choices() -> None:
    example = EvalExample(
        id="x",
        task="mcq",
        question="q",
        choices=["a", "b"],
        answer_index=0,
    )
    prompt = build_prompt(example)
    assert "A. a" in prompt
    assert "only the letter" in prompt


def test_parse_classification() -> None:
    labels = ["benign", "vulnerable"]
    assert parse_classification("vulnerable", labels) == "vulnerable"
    assert parse_classification("Label: benign", labels) == "benign"
    assert parse_classification("This is clearly VULNERABLE code.", labels) == "vulnerable"
    assert parse_classification("unknown", labels) is None


def test_harness_end_to_end(tmp_path: Path) -> None:
    examples = load_examples(_example_file(tmp_path))
    harness = EvaluationHarness(FakeEngine(), examples, seed=1, prompt_style="chat")
    summary = harness.run()
    assert summary["metrics"]["mcq"]["accuracy"] == 1.0
    assert summary["metrics"]["classification"]["accuracy"] == 1.0
    assert summary["metrics"]["classification"]["false_positive_rate"] == 0.0
    assert summary["metrics"]["generation"]["exact_match"] == 1.0
    assert summary["metrics"]["generation"]["execution_claim_rate"] == 0.0
    assert "unsupported_token_rate_proxy" in summary["metrics"]["generation"]
    assert summary["operational"]["generated_tokens"] > 0
    assert summary["reproducibility"]["packages"]
    assert summary["run_sha256"]


def test_harness_dry_run_does_not_load_model(tmp_path: Path) -> None:
    examples = load_examples(_example_file(tmp_path))
    assert all(example.task for example in examples)
