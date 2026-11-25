"""Typed, hashable configuration for multi-source dataset builds.

A dataset configuration names the registered sources to include, where their
local inputs live, optional pinned revisions, per-source limits, and the global
cleaning/splitting parameters. The configuration is deliberately separate from
``data/sources.yaml``: the registry describes *what a source is and how it is
licensed*, while a configuration describes *what this build consumes*.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, ClassVar

import yaml

from cyberlite.data.splits import SplitRatios

PIPELINE_VERSION = "2.0.0"

DEFAULT_ALLOWED_LICENSES = [
    "Apache-2.0",
    "MIT",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "BSD-4-Clause-UC",
    "CC-BY-4.0",
    "CC-BY-SA-4.0",
    "CC0-1.0",
    "Public-Domain",
    "Synthetic",
    "MITRE-ATTACK",
    "MITRE-CWE",
    "GPL-1.0-or-later",
    "GPL-2.0-only",
    "GPL-2.0-or-later",
    "GPL-3.0-or-later",
    "Linux-man-pages-copyleft",
    "Linux-man-pages-1-para",
    "IETF-Trust",
    "OpenSSH",
    "Mixed-SPDX",
]


@dataclass(frozen=True)
class QualityThresholds:
    """Global quality gates applied after normalization and cleaning."""

    min_prompt_chars: int = 1
    min_response_chars: int = 120
    max_response_chars: int = 20_000
    min_total_chars: int = 80
    max_total_chars: int = 200_000
    max_repeated_line_ratio: float = 0.35
    min_unique_token_ratio: float = 0.0
    max_url_ratio: float = 0.45
    max_boilerplate_ratio: float = 0.50
    max_navigation_line_ratio: float = 0.25
    reject_pii: bool = True
    reject_unsupported_absolute_claims: bool = False
    max_sequence_tokens: int = 2048

    def __post_init__(self) -> None:
        for name in (
            "min_prompt_chars",
            "min_response_chars",
            "max_response_chars",
            "min_total_chars",
            "max_total_chars",
            "max_sequence_tokens",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"quality.{name} must be non-negative")
        if self.max_response_chars < self.min_response_chars:
            raise ValueError("quality.max_response_chars must be >= min_response_chars")
        for name in (
            "max_repeated_line_ratio",
            "min_unique_token_ratio",
            "max_url_ratio",
            "max_boilerplate_ratio",
            "max_navigation_line_ratio",
        ):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"quality.{name} must be between 0 and 1")


@dataclass
class SourceRunConfig:
    """How one registered source participates in a build."""

    name: str
    include: bool = True
    paths: list[str] = field(default_factory=list)
    url: str = ""
    archive_url: str = ""
    revision: str = ""
    sha256: str = ""
    max_records: int | None = None
    group: str = ""
    license_override: str = ""
    options: dict[str, Any] = field(default_factory=dict)

    _ALLOWED: ClassVar[set[str]] = {
        "name",
        "include",
        "paths",
        "url",
        "archive_url",
        "revision",
        "sha256",
        "max_records",
        "group",
        "license_override",
        "options",
    }

    @classmethod
    def from_dict(cls, name: str, payload: dict[str, Any]) -> SourceRunConfig:
        if not isinstance(payload, dict):
            raise ValueError(f"source selection {name!r} must be a mapping")
        unknown = set(payload) - cls._ALLOWED
        if unknown:
            raise ValueError(f"source selection {name!r} has unknown fields: {sorted(unknown)}")
        data = {key: value for key, value in payload.items() if key != "name"}
        paths = data.get("paths", [])
        if isinstance(paths, str):
            paths = [paths]
        if not isinstance(paths, list) or not all(isinstance(item, str) for item in paths):
            raise ValueError(f"source selection {name!r} paths must be a string or list")
        max_records = data.get("max_records")
        if max_records is not None:
            max_records = int(max_records)
            if max_records < 0:
                raise ValueError(f"source selection {name!r} max_records must be non-negative")
        options = data.get("options", {})
        if not isinstance(options, dict):
            raise ValueError(f"source selection {name!r} options must be a mapping")
        return cls(
            name=name,
            include=bool(data.get("include", True)),
            paths=list(paths),
            url=str(data.get("url", "")),
            archive_url=str(data.get("archive_url", "")),
            revision=str(data.get("revision", "")),
            sha256=str(data.get("sha256", "")),
            max_records=max_records,
            group=str(data.get("group", "")),
            license_override=str(data.get("license_override", "")),
            options=dict(options),
        )


@dataclass
class DatasetConfig:
    """A complete, reproducible build description."""

    name: str = "pilot-v2"
    version: str = "2.0.0"
    seed: int = 42
    out_dir: str = "data/processed/pilot-v2"
    raw_dir: str = "data/raw"
    cache_dir: str = "data/cache"
    eval_dir: str = "data/evaluation"
    manifest_dir: str = "data/manifests/pilot-v2"
    registry: str = "data/sources.yaml"
    offline: bool = False
    download: bool = False
    tokenizer: str = "Qwen/Qwen3.5-0.8B"
    tokenizer_local_only: bool = True
    ratios: SplitRatios = field(default_factory=lambda: SplitRatios(0.9, 0.05, 0.05))
    allowed_licenses: list[str] = field(default_factory=lambda: list(DEFAULT_ALLOWED_LICENSES))
    redact: bool = True
    min_chars: int = 120
    max_chars: int = 200_000
    dedup_threshold: int = 3
    contamination_n: int = 13
    contamination_threshold: float = 0.2
    contamination_group_quarantine: bool = True
    group_splits: bool = True
    verify_split_leakage: bool = True
    include_sources: list[str] = field(default_factory=list)
    exclude_sources: list[str] = field(default_factory=list)
    limits: dict[str, int] = field(default_factory=dict)
    quality: QualityThresholds = field(default_factory=QualityThresholds)
    sources: list[SourceRunConfig] = field(default_factory=list)
    config_path: str = ""
    base_dir: str = "."

    _TOP_LEVEL: ClassVar[set[str]] = {
        "schema_version",
        "name",
        "version",
        "seed",
        "out_dir",
        "raw_dir",
        "cache_dir",
        "eval_dir",
        "manifest_dir",
        "registry",
        "offline",
        "download",
        "tokenizer",
        "tokenizer_local_only",
        "split",
        "ratios",
        "allowed_licenses",
        "redact",
        "min_chars",
        "max_chars",
        "dedup_threshold",
        "contamination_n",
        "contamination_threshold",
        "contamination_group_quarantine",
        "group_splits",
        "verify_split_leakage",
        "include_sources",
        "exclude_sources",
        "limits",
        "quality",
        "sources",
        "base_dir",
    }

    @classmethod
    def load(cls, path: str | Path) -> DatasetConfig:
        config_path = Path(path).resolve()
        payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("dataset config root must be a mapping")
        version = int(payload.pop("schema_version", 1))
        if version != 1:
            raise ValueError(f"unsupported dataset config schema: {version}")
        unknown = set(payload) - cls._TOP_LEVEL
        if unknown:
            raise ValueError(f"dataset config has unknown fields: {sorted(unknown)}")

        base_dir = Path(
            payload.get("base_dir")
            or (
                config_path.parent.parent
                if config_path.parent.name == "configs"
                else config_path.parent
            )
        ).resolve()

        split_payload = payload.get("split", payload.get("ratios", {})) or {}
        if not isinstance(split_payload, dict):
            raise ValueError("split must be a mapping with train/validation/test")
        ratios = SplitRatios(
            float(split_payload.get("train", 0.9)),
            float(split_payload.get("validation", 0.05)),
            float(split_payload.get("test", 0.05)),
        )

        quality_payload = payload.get("quality", {}) or {}
        if not isinstance(quality_payload, dict):
            raise ValueError("quality must be a mapping")
        quality_unknown = set(quality_payload) - set(QualityThresholds.__dataclass_fields__)
        if quality_unknown:
            raise ValueError(f"quality has unknown fields: {sorted(quality_unknown)}")
        quality = QualityThresholds(**quality_payload)

        raw_sources = payload.get("sources", [])
        sources: list[SourceRunConfig] = []
        if isinstance(raw_sources, dict):
            for name, selection in raw_sources.items():
                if selection is None:
                    selection = {}
                sources.append(SourceRunConfig.from_dict(str(name), selection))
        elif isinstance(raw_sources, list):
            for selection in raw_sources:
                if not isinstance(selection, dict) or "name" not in selection:
                    raise ValueError("each source selection needs a name")
                name = str(selection["name"])
                sources.append(SourceRunConfig.from_dict(name, selection))
        else:
            raise ValueError("sources must be a mapping or a list")

        names = [source.name for source in sources]
        if len(names) != len(set(names)):
            raise ValueError("duplicate source selection names")

        allowed = payload.get("allowed_licenses", list(DEFAULT_ALLOWED_LICENSES))
        if not isinstance(allowed, list) or not all(isinstance(item, str) for item in allowed):
            raise ValueError("allowed_licenses must be a list of strings")

        limits = payload.get("limits", {}) or {}
        if not isinstance(limits, dict):
            raise ValueError("limits must be a mapping")

        return cls(
            name=str(payload.get("name", "pilot-v2")),
            version=str(payload.get("version", "2.0.0")),
            seed=int(payload.get("seed", 42)),
            out_dir=str(payload.get("out_dir", "data/processed/pilot-v2")),
            raw_dir=str(payload.get("raw_dir", "data/raw")),
            cache_dir=str(payload.get("cache_dir", "data/cache")),
            eval_dir=str(payload.get("eval_dir", "data/evaluation")),
            manifest_dir=str(payload.get("manifest_dir", "data/manifests/pilot-v2")),
            registry=str(payload.get("registry", "data/sources.yaml")),
            offline=bool(payload.get("offline", False)),
            download=bool(payload.get("download", False)),
            tokenizer=str(payload.get("tokenizer", "Qwen/Qwen3.5-0.8B")),
            tokenizer_local_only=bool(payload.get("tokenizer_local_only", True)),
            ratios=ratios,
            allowed_licenses=list(allowed),
            redact=bool(payload.get("redact", True)),
            min_chars=int(payload.get("min_chars", 120)),
            max_chars=int(payload.get("max_chars", 200_000)),
            dedup_threshold=int(payload.get("dedup_threshold", 3)),
            contamination_n=int(payload.get("contamination_n", 13)),
            contamination_threshold=float(payload.get("contamination_threshold", 0.2)),
            contamination_group_quarantine=bool(
                payload.get("contamination_group_quarantine", True)
            ),
            group_splits=bool(payload.get("group_splits", True)),
            verify_split_leakage=bool(payload.get("verify_split_leakage", True)),
            include_sources=[str(item) for item in payload.get("include_sources", [])],
            exclude_sources=[str(item) for item in payload.get("exclude_sources", [])],
            limits={str(key): int(value) for key, value in limits.items()},
            quality=quality,
            sources=sorted(sources, key=lambda item: item.name),
            config_path=str(config_path),
            base_dir=str(base_dir),
        )

    # -- path handling -------------------------------------------------
    @property
    def base_path(self) -> Path:
        return Path(self.base_dir)

    def resolve(self, value: str | Path) -> Path:
        path = Path(value)
        return path if path.is_absolute() else self.base_path / path

    def resolve_sources(self) -> list[SourceRunConfig]:
        """Return selected sources, honouring include/exclude lists and limits."""

        include = set(self.include_sources)
        exclude = set(self.exclude_sources)
        overlap = include & exclude
        if overlap:
            raise ValueError(f"sources cannot be both included and excluded: {sorted(overlap)}")
        if include and exclude and not include.isdisjoint(exclude):
            raise ValueError("include_sources and exclude_sources overlap")
        selected: list[SourceRunConfig] = []
        for source in self.sources:
            if include and source.name not in include:
                continue
            if source.name in exclude or not source.include:
                continue
            if source.name in self.limits and source.max_records is None:
                source = SourceRunConfig(
                    **{
                        **asdict(source),
                        "max_records": self.limits[source.name],
                    }
                )
            selected.append(source)
        unknown_include = include - {source.name for source in self.sources}
        unknown_exclude = exclude - {source.name for source in self.sources}
        if unknown_include or unknown_exclude:
            raise ValueError(
                "include/exclude references unknown source selections: "
                f"{sorted(unknown_include | unknown_exclude)}"
            )
        return selected

    def canonical(self) -> dict[str, Any]:
        """Return a stable representation used for the configuration hash."""

        payload = asdict(self)
        for key in (
            "config_path",
            "base_dir",
            "out_dir",
            "raw_dir",
            "cache_dir",
            "eval_dir",
            "manifest_dir",
            "offline",
            "download",
            "tokenizer_local_only",
        ):
            payload.pop(key, None)
        payload["ratios"] = asdict(self.ratios)
        payload["quality"] = asdict(self.quality)
        payload["sources"] = [
            {key: value for key, value in asdict(source).items()} for source in self.sources
        ]
        payload["sources"].sort(key=lambda item: item["name"])
        payload["allowed_licenses"] = sorted(self.allowed_licenses)
        payload["include_sources"] = sorted(self.include_sources)
        payload["exclude_sources"] = sorted(self.exclude_sources)
        payload["limits"] = dict(sorted(self.limits.items()))
        return payload

    def sha256(self) -> str:
        canonical = json.dumps(
            self.canonical(), sort_keys=True, separators=(",", ":"), ensure_ascii=True
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
