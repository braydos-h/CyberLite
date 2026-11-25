"""Language profiles and prompt construction for autocomplete."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

FIM_PREFIX = "<|fim_prefix|>"
FIM_SUFFIX = "<|fim_suffix|>"
FIM_MIDDLE = "<|fim_middle|>"
FIM_PAD = "<|fim_pad|>"


@dataclass(frozen=True)
class LanguageProfile:
    name: str
    extensions: tuple[str, ...]
    fence: str
    comment: str
    notes: str = ""


LANGUAGES: dict[str, LanguageProfile] = {
    "bash": LanguageProfile("bash", (".sh", ".bash", ".zsh"), "bash", "#"),
    "python": LanguageProfile("python", (".py", ".pyi"), "python", "#"),
    "powershell": LanguageProfile("powershell", (".ps1", ".psm1", ".psd1"), "powershell", "#"),
    "yara": LanguageProfile("yara", (".yar", ".yara"), "yara", "//"),
    "sigma": LanguageProfile("sigma", (".yml", ".yaml"), "yaml", "#"),
    "regex": LanguageProfile("regex", (".re", ".regex"), "regex", "#"),
    "bpf": LanguageProfile("bpf", (".bpf",), "text", "#"),
    "tcpdump": LanguageProfile("tcpdump", (".tcpdump",), "bash", "#"),
    "nginx": LanguageProfile("nginx", (".conf",), "nginx", "#"),
    "dockerfile": LanguageProfile("dockerfile", ("Dockerfile",), "dockerfile", "#"),
    "sql": LanguageProfile("sql", (".sql",), "sql", "--"),
    "json": LanguageProfile("json", (".json",), "json", "//"),
    "generic": LanguageProfile("generic", (), "text", "#"),
}

_EXTENSION_INDEX: dict[str, str] = {
    extension.lower(): name
    for name, profile in LANGUAGES.items()
    for extension in profile.extensions
}


def get_language(name: str) -> LanguageProfile:
    normalized = name.strip().lower()
    aliases = {
        "sh": "bash",
        "shell": "bash",
        "linux": "bash",
        "zsh": "bash",
        "ps1": "powershell",
        "pwsh": "powershell",
        "yml": "sigma",
        "yaml": "sigma",
        "regexp": "regex",
        "rules": "yara",
        "config": "generic",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in LANGUAGES:
        return LANGUAGES["generic"]
    return LANGUAGES[normalized]


def detect_language(*, filename: str | None = None, explicit: str | None = None) -> LanguageProfile:
    if explicit and explicit.lower() not in {"auto", ""}:
        return get_language(explicit)
    if filename:
        path = Path(filename)
        if path.name.lower() == "dockerfile":
            return LANGUAGES["dockerfile"]
        suffix = path.suffix.lower()
        if suffix in _EXTENSION_INDEX:
            return LANGUAGES[_EXTENSION_INDEX[suffix]]
    return LANGUAGES["generic"]


def build_fim_prompt(prefix: str, suffix: str = "") -> str:
    return f"{FIM_PREFIX}{prefix}{FIM_SUFFIX}{suffix}{FIM_MIDDLE}"


def build_prefix_chat_messages(
    prefix: str, suffix: str, profile: LanguageProfile
) -> list[dict[str, str]]:
    suffix_block = (
        f"\n\nText that follows the cursor:\n```{profile.fence}\n{suffix}\n```" if suffix else ""
    )
    return [
        {
            "role": "system",
            "content": (
                "You are a precise code and command completion engine. Continue the user's "
                "content at the cursor. Output only the text that belongs at the cursor, with "
                "no explanation and no markdown fences. Never invent credentials. Prefer safe, "
                "defensive defaults."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Language: {profile.name}\n\nBefore the cursor:\n```{profile.fence}\n"
                f"{prefix}\n```{suffix_block}\n\nCompletion at the cursor:"
            ),
        },
    ]


_CODE_FENCE_RE = re.compile(r"^\s*```[a-zA-Z0-9_+-]*\s*\n(.*?)\n```\s*$", re.DOTALL)
_LEADING_LABEL_RE = re.compile(
    r"^\s*(?:completion|suggestion|output|code|answer)\s*:\s*", re.IGNORECASE
)


def sanitize_completion(text: str, prefix: str = "") -> str:
    """Remove common model artifacts without changing the completion's meaning."""

    text = text.replace(FIM_PAD, "").replace(FIM_MIDDLE, "").replace(FIM_SUFFIX, "")
    text = text.replace(FIM_PREFIX, "")
    fence = _CODE_FENCE_RE.match(text)
    if fence:
        text = fence.group(1)
    text = _LEADING_LABEL_RE.sub("", text)
    if text.startswith(prefix) and prefix:
        text = text[len(prefix) :]
        if text.startswith((" ", "\t")) and not prefix.endswith((" ", "\t", "\n")):
            text = text[1:]
    text = text.rstrip()
    return text
