"""Heading-aware Markdown segmentation that preserves code blocks.

Most public security documentation is Markdown. Splitting it at a fixed
character boundary cuts code samples and lists in half, so this module segments
on headings, keeps fenced code intact, and only falls back to paragraph
boundaries when a single section is too long.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from pathlib import Path

_FENCE_RE = re.compile(r"^(\s*)(```+|~~~+)(.*)$")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_FRONT_MATTER_RE = re.compile(r"\A---\s*\n.*?\n---\s*\n", re.DOTALL)
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_INLINE_LINK_RE = re.compile(r"!?\[([^\]]*)\]\((?:[^()]|\([^)]*\))*\)")
_REFERENCE_LINK_RE = re.compile(r"\[([^\]]+)\]\[[^\]]*\]")
_REFERENCE_DEF_RE = re.compile(r"^\s*\[[^\]]+\]:\s+\S+.*$", re.MULTILINE)
_HTML_TAG_RE = re.compile(r"</?[A-Za-z][^>]*>")
_NAV_LINE_RES = [
    re.compile(r"^\s*\[[^\]]+\]\([^)]+\)\s*$"),
    re.compile(r"^\s*[-*+]\s+\[[^\]]+\]\([^)]+\)\s*$"),
    re.compile(r"^\s*!\[[^\]]*\]\([^)]*\)\s*$"),
    re.compile(r"^\s*<a\b[^>]*>.*?</a>\s*$", re.IGNORECASE),
    re.compile(
        r"^\s*(?:back to top|edit this page|previous|next|table of contents|contents)\s*$",
        re.IGNORECASE,
    ),
    re.compile(r"^\s*(?:home|docs?)\s*[»>/|]\s*", re.IGNORECASE),
    re.compile(r"^\s*(?:---|\*\*\*|___)\s*$"),
]
_BOILERPLATE_HEADINGS = {
    "table of contents",
    "contents",
    "contributing",
    "contributors",
    "acknowledgements",
    "acknowledgments",
    "license",
    "licence",
    "changelog",
    "change log",
    "references",
    "further reading",
    "see also",
    "navigation",
    "footer",
}
_NAV_WORDS = {
    "previous",
    "next",
    "back to top",
    "edit this page",
    "table of contents",
    "contents",
}


@dataclass
class MarkdownSection:
    heading: str
    level: int
    body: str
    path: str
    anchor: str
    start_line: int
    code_blocks: int = 0
    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def title_path(self) -> str:
        return self.heading

    def as_text(self) -> str:
        heading = "#" * max(1, self.level) + " " + self.heading
        return f"{heading}\n\n{self.body}".strip()


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "section"


def _strip_html_outside_fences(text: str) -> str:
    lines = text.split("\n")
    output: list[str] = []
    in_fence = False
    for line in lines:
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            output.append(line)
            continue
        if in_fence:
            output.append(line)
        else:
            output.append(_HTML_TAG_RE.sub("", line))
    return "\n".join(output)


def _clean_inline_markdown(text: str) -> str:
    """Remove link targets, images, and reference definitions outside fences."""

    lines = text.split("\n")
    output: list[str] = []
    in_fence = False
    for line in lines:
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            output.append(line)
            continue
        if in_fence:
            output.append(line)
            continue
        line = _INLINE_LINK_RE.sub(lambda match: match.group(1), line)
        line = _REFERENCE_LINK_RE.sub(lambda match: match.group(1), line)
        if _REFERENCE_DEF_RE.match(line):
            continue
        line = html.unescape(line)
        output.append(line.rstrip())
    return "\n".join(output)


def _is_navigation_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if stripped.lower() in _NAV_WORDS:
        return True
    return any(pattern.match(stripped) for pattern in _NAV_LINE_RES)


def _remove_navigation(text: str) -> tuple[str, float]:
    lines = text.split("\n")
    kept: list[str] = []
    nonempty = 0
    navigation = 0
    in_fence = False
    for line in lines:
        if _FENCE_RE.match(line):
            in_fence = not in_fence
        if not in_fence and _is_navigation_line(line):
            navigation += 1
            continue
        if line.strip():
            nonempty += 1
        kept.append(line)
    ratio = navigation / max(1, nonempty + navigation)
    return "\n".join(kept), ratio


def _count_code_blocks(text: str) -> int:
    count = 0
    in_fence = False
    for line in text.split("\n"):
        if _FENCE_RE.match(line):
            if not in_fence:
                count += 1
            in_fence = not in_fence
    return count


def _unclosed_fence(text: str) -> bool:
    in_fence = False
    for line in text.split("\n"):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
    return in_fence


def _split_long_section(
    heading: str, level: int, body: str, *, max_chars: int
) -> list[tuple[str, int, str]]:
    """Split on blank lines outside code fences, never inside a fence."""

    if len(body) <= max_chars:
        return [(heading, level, body)]
    paragraphs: list[str] = []
    current: list[str] = []
    in_fence = False
    for line in body.split("\n"):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
        if not in_fence and not line.strip() and current:
            paragraphs.append("\n".join(current).strip())
            current = []
            continue
        current.append(line)
    if current:
        paragraphs.append("\n".join(current).strip())
    chunks: list[str] = []
    buffer: list[str] = []
    size = 0
    for paragraph in paragraphs:
        if buffer and size + len(paragraph) + 2 > max_chars:
            chunks.append("\n\n".join(buffer).strip())
            buffer = []
            size = 0
        buffer.append(paragraph)
        size += len(paragraph) + 2
    if buffer:
        chunks.append("\n\n".join(buffer).strip())
    return [
        (f"{heading} (part {index + 1})" if len(chunks) > 1 else heading, level, chunk)
        for index, chunk in enumerate(chunks)
        if chunk
    ]


def _iter_lines_with_fences(text: str) -> list[tuple[int, str, bool]]:
    """Return ``(line_number, line, in_fence_before_line)`` triples."""

    rows: list[tuple[int, str, bool]] = []
    in_fence = False
    for line_number, line in enumerate(text.split("\n"), start=1):
        rows.append((line_number, line, in_fence))
        if _FENCE_RE.match(line):
            in_fence = not in_fence
    return rows


def segment_markdown(
    text: str,
    *,
    path: str = "",
    min_section_chars: int = 200,
    max_section_chars: int = 6000,
    max_heading_level: int = 3,
    drop_boilerplate_headings: bool = True,
) -> list[MarkdownSection]:
    """Split Markdown into heading-delimited, code-safe sections."""

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _FRONT_MATTER_RE.sub("", text)
    text = _HTML_COMMENT_RE.sub("", text)
    text = _strip_html_outside_fences(text)
    text = _clean_inline_markdown(text)
    text = _REFERENCE_DEF_RE.sub("", text)

    rows = _iter_lines_with_fences(text)
    raw_sections: list[tuple[str, int, list[str], int]] = []
    current_heading = "Overview"
    current_level = 1
    current_lines: list[str] = []
    current_start = 1
    in_fence = False
    saw_heading = False

    def flush() -> None:
        nonlocal current_lines, current_heading, current_level, current_start
        body = "\n".join(current_lines).strip()
        if body or saw_heading:
            raw_sections.append((current_heading, current_level, current_lines, current_start))
        current_lines = []

    for line_number, line, fence_before in rows:
        is_fence = bool(_FENCE_RE.match(line))
        heading_match = None if fence_before or in_fence else _HEADING_RE.match(line)
        if heading_match and not is_fence:
            flush()
            saw_heading = True
            current_level = len(heading_match.group(1))
            current_heading = heading_match.group(2).strip()
            current_start = line_number + 1
            current_lines = []
            if is_fence:
                in_fence = not in_fence
            continue
        current_lines.append(line)
        if is_fence:
            in_fence = not in_fence

    flush()

    sections: list[MarkdownSection] = []
    for heading, level, lines, start_line in raw_sections:
        if level > max_heading_level:
            # Attach deep subsections to their parent rather than dropping them.
            if sections:
                sections[-1].body += "\n\n" + "\n".join(lines).strip()
                sections[-1].code_blocks = _count_code_blocks(sections[-1].body)
                continue
            level = max_heading_level
        body = "\n".join(lines).strip()
        if not body:
            continue
        if drop_boilerplate_headings and heading.strip().lower() in _BOILERPLATE_HEADINGS:
            continue
        body, navigation_ratio = _remove_navigation(body)
        body = re.sub(r"\n{3,}", "\n\n", body).strip()
        if _unclosed_fence(body):
            # A truncated input must not produce an unterminated code block.
            body += "\n```"
        if len(body) < min_section_chars:
            continue
        for part_heading, part_level, part_body in _split_long_section(
            heading, level, body, max_chars=max_section_chars
        ):
            sections.append(
                MarkdownSection(
                    heading=part_heading,
                    level=part_level,
                    body=part_body,
                    path=path,
                    anchor=slugify(heading),
                    start_line=start_line,
                    code_blocks=_count_code_blocks(part_body),
                    metadata={"navigation_line_ratio": round(navigation_ratio, 3)},
                )
            )
    return sections


def load_markdown_sections(
    path: str | Path,
    *,
    min_section_chars: int = 200,
    max_section_chars: int = 6000,
    max_heading_level: int = 3,
) -> list[MarkdownSection]:
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8", errors="replace")
    return segment_markdown(
        text,
        path=str(file_path),
        min_section_chars=min_section_chars,
        max_section_chars=max_section_chars,
        max_heading_level=max_heading_level,
    )
