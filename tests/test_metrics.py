from __future__ import annotations

from cyberlite.evaluation import metrics


def test_accuracy_and_exact_match() -> None:
    assert metrics.accuracy([1, 0, 1], [1, 1, 1]) == 2 / 3
    assert metrics.exact_match(["Hello, world!"], ["hello world"]) == 1.0


def test_token_f1() -> None:
    assert (
        metrics.token_f1(
            "parameterized queries prevent injection", "parameterized queries prevent injection"
        )
        == 1.0
    )
    assert metrics.token_f1("completely unrelated", "parameterized queries") == 0.0
    assert 0 < metrics.token_f1("parameterized query defense", "parameterized queries defense") < 1


def test_mcq_parse_formats() -> None:
    choices = ["alpha", "beta", "gamma", "delta"]
    assert metrics.parse_mcq_answer("B", choices) == 1
    assert metrics.parse_mcq_answer("Answer: C", choices) == 2
    assert metrics.parse_mcq_answer("The correct option is (D).", choices) == 3
    assert metrics.parse_mcq_answer("beta", choices) == 1
    assert metrics.parse_mcq_answer("no idea", choices) is None
    assert metrics.parse_mcq_answer("Z", choices) is None


def test_mcq_parse_answer_sets() -> None:
    choices = ["alpha", "beta", "gamma", "delta"]
    assert metrics.parse_mcq_answer_set("B", choices) == [1]
    assert metrics.parse_mcq_answer_set("AC", choices) == [0, 2]
    assert metrics.parse_mcq_answer_set("A, C", choices) == [0, 2]
    assert metrics.parse_mcq_answer_set("Answer: D", choices) == [3]
    assert metrics.parse_mcq_answer_set("CA", choices) == [0, 2]
    assert metrics.parse_mcq_answer_set("no idea", choices) is None
    assert metrics.parse_mcq_answer_set("Z", choices) is None


def test_macro_f1_and_fpr() -> None:
    predictions = ["malicious", "benign", "malicious", "benign"]
    references = ["malicious", "benign", "benign", "benign"]
    assert metrics.macro_f1(predictions, references) == 0.7333333333333334
    assert (
        metrics.false_positive_rate(predictions, references, positive_label="malicious")
        == 0.3333333333333333
    )
    assert metrics.false_positive_rate(["benign"], ["benign"], positive_label="malicious") == 0.0
    assert (
        metrics.false_positive_rate(["malicious"], ["malicious"], positive_label="malicious")
        is None
    )


def test_refusal_and_execution_claims() -> None:
    assert metrics.refusal_rate(["I cannot help with that."]) == 1.0
    assert metrics.execution_claim_rate(["I ran the command successfully."]) == 1.0
    assert metrics.execution_claim_rate(["Run the command to verify."]) == 0.0


def test_grounding_proxy() -> None:
    evidence = "parameterized queries separate code from data"
    assert metrics.unsupported_token_rate("parameterized queries", evidence) == 0.0
    assert metrics.unsupported_token_rate("totally unsupported claim", evidence) == 1.0


def test_syntax_valid_rate_does_not_execute() -> None:
    assert metrics.syntax_valid_rate(["x = 1\nprint(x)"]) == 1.0
    assert metrics.syntax_valid_rate(["def broken(:"]) == 0.0
    assert metrics.syntax_valid_rate(["x = 1"], language="bash") is None


def test_citation_ids() -> None:
    assert metrics.citation_ids("As shown in [S1] and [S3].") == {1, 3}
    assert metrics.citation_precision(["[S1] [S9]"], [1, 2]) == 0.5


def test_bootstrap_ci_bounds() -> None:
    low, high = metrics.bootstrap_accuracy_ci([1, 1, 0, 1], [1, 1, 1, 1], seed=1)
    assert 0.0 <= low <= high <= 1.0


def test_performance_per_billion() -> None:
    assert metrics.performance_per_billion(0.5, 0.8) == 62.5
    assert metrics.performance_per_billion(0.5, 0) is None
    assert metrics.performance_per_dollar(0.5, 10) == 5.0
