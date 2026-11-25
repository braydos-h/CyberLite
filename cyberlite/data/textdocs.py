"""Parsers for roff manual pages and plain-text IETF RFCs.

These formats are common in Linux and networking documentation. Both parsers
keep indented examples and diagrams intact, emit section-level units, and skip
navigation, copyright, and author boilerplate.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_ROFF_COMMENT_RE = re.compile(r"^[.'\"]\\\"")
_ROFF_MACRO_RE = re.compile(r"^\.(?P<macro>[A-Za-z][A-Za-z0-9]*)\s*(?P<args>.*)$")
_ROFF_ARG_RE = re.compile(r'"([^"]*)"|(\S+)')
_RFC_HEADING_RE = re.compile(
    r"^(?P<num>\d+(?:\.\d+)*\.?|Appendix\s+[A-Z]\.)\s{1,4}(?P<title>[A-Z][^\n]{1,90})$"
)
_RFC_FOOTER_RE = re.compile(r"^\s*.*\[Page\s+\d+\]\s*$")
_RFC_PAGE_HEADER_RE = re.compile(
    r"^RFC\s+\d+\s{2,}.*\s{2,}(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\s*$"
)

_ROFF_ESCAPES = {
    r"\-": "-",
    r"\&": "",
    r"\e": "\\",
    r"\\": "\\",
    r"\(aq": "'",
    r"\(dq": '"',
    r"\(lq": '"',
    r"\(rq": '"',
    r"\(em": "—",
    r"\(en": "\u2013",
    r"\(bu": "•",
    r"\(co": "©",
    r"\(rg": "®",
    r"\(tm": "™",
    r"\*(lq": '"',
    r"\*(rq": '"',
    r"\*(Tm": "(TM)",
    r"\*(R": "(R)",
    r"\*(C": "(C)",
    r"\~": " ",
    r"\ ": " ",
    r"\0": " ",
    r"\|": "",
    r"\^": "",
}
_SKIP_SH = {
    "name",
    "synopsis",
    "library",
    "author",
    "authors",
    "copyright",
    "colophon",
    "reporting bugs",
    "availability",
    "history",
}
_UNNUMBERED_SKIP = {
    "abstract",
    "status of this memo",
    "copyright notice",
    "table of contents",
    "acknowledgements",
    "acknowledgments",
    "authors' addresses",
    "author's address",
    "references",
    "index",
}
_SKIP_RFC = {
    "abstract",
    "status of this memo",
    "copyright notice",
    "table of contents",
    "acknowledgements",
    "acknowledgments",
    "authors' addresses",
    "author's address",
    "index",
}


@dataclass
class TextSection:
    heading: str
    body: str
    path: str
    metadata: dict[str, object] = field(default_factory=dict)

    def as_text(self) -> str:
        return f"# {self.heading}\n\n{self.body}".strip()


@dataclass
class RoffDocument:
    title: str
    section: str
    source: str
    manual: str
    spdx_license: str
    sections: list[TextSection]


@dataclass
class RfcDocument:
    number: str
    title: str
    category: str
    date: str
    sections: list[TextSection]


def _split_roff_args(value: str) -> list[str]:
    return [first or second for first, second in _ROFF_ARG_RE.findall(value)]


def _roff_unescape(text: str) -> str:
    for source, replacement in _ROFF_ESCAPES.items():
        text = text.replace(source, replacement)
    text = re.sub(r"\\f(?:\[[^\]]*\]|\([A-Za-z]{2}|[A-Za-z0-9])", "", text)
    text = re.sub(r"\\s[+-]?\d+", "", text)
    text = re.sub(r"\\n\([A-Za-z0-9]{2}", "", text)
    text = re.sub(r"\\n\[[^\]]*\]", "", text)
    text = re.sub(r"\\\*\([A-Za-z0-9]{2}", "", text)
    text = re.sub(r"\\\*\[[^\]]*\]", "", text)
    return text


def _flush_roff_section(
    sections: list[TextSection],
    path: str,
    sh: str,
    ss: str,
    body: list[str],
    *,
    min_chars: int,
    metadata: dict[str, object],
) -> None:
    text = "\n".join(body).strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    if text.count("```") % 2:
        text += "\n```"
    if len(text) < min_chars:
        return
    heading = sh if not ss else f"{sh} — {ss}"
    sections.append(TextSection(heading=heading, body=text, path=path, metadata=dict(metadata)))


def parse_roff(
    path: str | Path,
    *,
    min_section_chars: int = 200,
    max_section_chars: int = 6000,
) -> RoffDocument:
    file_path = Path(path)
    raw_lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
    spdx = ""
    for line in raw_lines[:80]:
        if "SPDX-License-Identifier:" in line:
            spdx = line.split("SPDX-License-Identifier:", 1)[1].strip().strip("*/").strip()
            break

    title = file_path.stem
    section = ""
    source = ""
    manual = ""
    sections: list[TextSection] = []
    sh = ""
    ss = ""
    body: list[str] = []
    no_fill = False
    pending_tp = False
    metadata: dict[str, object] = {"parser": "roff", "spdx_license": spdx}
    index = 0

    def flush() -> None:
        nonlocal body
        if sh and sh.lower() not in _SKIP_SH:
            _flush_roff_section(
                sections,
                str(file_path),
                sh,
                ss,
                body,
                min_chars=min_section_chars,
                metadata=metadata,
            )
        body = []

    while index < len(raw_lines):
        line = raw_lines[index]
        index += 1
        if _ROFF_COMMENT_RE.match(line):
            continue
        macro_match = _ROFF_MACRO_RE.match(line)
        if macro_match:
            macro = macro_match.group("macro")
            args = _split_roff_args(macro_match.group("args"))
            joined = " ".join(args)
            if macro == "TH":
                if args:
                    title = _roff_unescape(args[0])
                if len(args) > 1:
                    section = _roff_unescape(args[1])
                source = _roff_unescape(args[2]) if len(args) > 2 else ""
                manual = _roff_unescape(args[3]) if len(args) > 3 else ""
                continue
            if macro == "Dt":
                if args:
                    title = _roff_unescape(args[0])
                if len(args) > 1:
                    section = _roff_unescape(args[1])
                continue
            if macro in {"Dd", "Os"}:
                continue
            if macro == "Bd":
                body.append("```")
                continue
            if macro == "Ed":
                body.append("```")
                continue
            if macro == "Bl":
                body.append("")
                continue
            if macro == "El":
                body.append("")
                continue
            if macro == "Pp":
                body.append("")
                continue
            if macro == "It":
                pending_tp = False
                body.append("")
                if args:
                    term_args = (
                        args[1:]
                        if args[0]
                        in {
                            "Cm",
                            "Fl",
                            "Ar",
                            "Op",
                            "Pa",
                            "Dv",
                            "Ev",
                            "Ic",
                            "Em",
                            "Sy",
                            "Li",
                        }
                        else args
                    )
                    if term_args:
                        body.append(_roff_unescape(" ".join(term_args)))
                continue
            if macro == "Nm":
                if args:
                    body.append(_roff_unescape(joined))
                else:
                    body.append(title)
                continue
            if macro == "Nd":
                body.append("— " + _roff_unescape(joined))
                continue
            if macro == "Dl":
                body.append("")
                body.append(_roff_unescape(joined))
                continue
            if macro in {
                "Fl",
                "Ar",
                "Op",
                "Xr",
                "Pa",
                "Dv",
                "Ev",
                "Cm",
                "Ic",
                "Sx",
                "Em",
                "Sy",
                "Li",
                "No",
                "Ns",
                "Pf",
                "Tn",
                "Ux",
                "Bx",
                "Fx",
                "Ox",
                "Nx",
                "At",
                "Lb",
                "In",
                "Ft",
                "Fn",
                "Fa",
                "Vt",
                "Va",
                "Dq",
                "Sq",
                "Pq",
                "Qq",
                "Bq",
                "Brq",
                "Aq",
                "Eo",
                "Ec",
                "Sm",
                "Bk",
                "Ek",
                "Rs",
                "Re",
                "An",
                "Ad",
                "Cd",
                "Ms",
                "St",
                "Lk",
                "Mt",
            }:
                body.append(_roff_unescape(joined))
                continue
            if macro in {"SH", "Sh"}:
                flush()
                sh = _roff_unescape(joined).strip()
                ss = ""
                body = []
                continue
            if macro in {"SS", "Ss"}:
                flush()
                ss = _roff_unescape(joined).strip()
                body = []
                continue
            if macro in {"PP", "P", "LP", "sp", "br", "par"}:
                body.append("")
                continue
            if macro in {"IP"}:
                mark = _roff_unescape(args[0]).strip() if args else "•"
                if mark in {"", "\\-"}:
                    mark = "•"
                body.append("")
                body.append(f"{mark} " if mark != "•" else "• ")
                continue
            if macro in {"TP"}:
                pending_tp = True
                body.append("")
                continue
            if macro in {"nf", "EX"}:
                no_fill = True
                body.append("```")
                continue
            if macro in {"fi", "EE"}:
                no_fill = False
                body.append("```")
                continue
            if macro in {"B", "I", "SB", "SM", "BI", "BR", "IB", "IR", "RB", "RI"}:
                separator = " " if macro in {"B", "I", "SB", "SM", "BI", "IB"} else ""
                text = separator.join(_roff_unescape(part) for part in args)
                if pending_tp:
                    body.append(text)
                    pending_tp = False
                else:
                    body.append(text)
                continue
            if macro in {"ds", "de", "ie", "if", "el", "so", "nr", "tr", "rm", "rn"}:
                continue
            if macro in {"UR"}:
                continue
            if macro in {"UE"}:
                if args:
                    body.append(_roff_unescape(joined))
                continue
            # Unknown macro: keep its arguments as text when present.
            if joined:
                body.append(_roff_unescape(joined))
            continue

        text = _roff_unescape(line.rstrip())
        if not text:
            body.append("")
            continue
        if no_fill:
            body.append(text)
        else:
            body.append(text)

    flush()
    # Split very long sections at blank lines, preserving indented examples.
    expanded: list[TextSection] = []
    for section_item in sections:
        if len(section_item.body) <= max_section_chars:
            expanded.append(section_item)
            continue
        chunks = _split_preserving_fences(section_item.body, max_section_chars)
        for part, chunk in enumerate(chunks, start=1):
            expanded.append(
                TextSection(
                    heading=(
                        f"{section_item.heading} (part {part})"
                        if len(chunks) > 1
                        else section_item.heading
                    ),
                    body=chunk,
                    path=section_item.path,
                    metadata=dict(section_item.metadata),
                )
            )
    return RoffDocument(
        title=title,
        section=section,
        source=source,
        manual=manual,
        spdx_license=spdx,
        sections=expanded,
    )


def _strip_rfc_page_artifacts(text: str) -> str:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    cleaned: list[str] = []
    for line in lines:
        if "\f" in line:
            line = line.replace("\f", "")
        if _RFC_FOOTER_RE.match(line) or _RFC_PAGE_HEADER_RE.match(line):
            continue
        cleaned.append(line.rstrip())
    return "\n".join(cleaned)


def parse_rfc(
    path: str | Path,
    *,
    min_section_chars: int = 200,
    max_section_chars: int = 6000,
) -> RfcDocument:
    file_path = Path(path)
    text = _strip_rfc_page_artifacts(file_path.read_text(encoding="utf-8", errors="replace"))
    lines = text.split("\n")
    number = ""
    category = ""
    date = ""
    title = file_path.stem.upper()
    for line in lines[:40]:
        if match := re.search(r"Request for Comments:\s*(\d+)", line):
            number = match.group(1)
        if match := re.search(r"Category:\s*(.+?)\s*$", line):
            category = match.group(1)
        if match := re.search(
            r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}",
            line,
        ):
            date = match.group(0)
    # RFC front matter is a header block followed by a centred title. Older
    # RFCs have no Abstract, so find the first structural heading and read the
    # non-empty block above it.
    boundary = None
    for index, line in enumerate(lines[:200]):
        stripped = line.strip().lower()
        if stripped in {"abstract", "status of this memo", "table of contents"} or re.match(
            r"^\d+\.\s+(?:status of this memo|introduction|table of contents)", stripped
        ):
            boundary = index
            break
    title_block: list[str] = []
    if boundary is not None:
        cursor = boundary - 1
        while cursor >= 0 and not lines[cursor].strip():
            cursor -= 1
        while cursor >= 0 and lines[cursor].strip():
            title_block.append(lines[cursor].strip())
            cursor -= 1
    title_block = [
        line
        for line in reversed(title_block)
        if not re.match(
            r"^(Internet Engineering|Request for Comments|Category:|ISSN:|Obsoletes:|Updates:|"
            r"Stream:|Source:|Network Working Group|BCP:|STD:|FYI:)",
            line,
        )
        and not re.search(
            r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}$",
            line,
        )
    ]
    if title_block:
        title = " ".join(title_block)
    sections: list[TextSection] = []
    current_num = ""
    current_title = ""
    body: list[str] = []
    metadata = {"parser": "rfc", "rfc": number, "category": category, "date": date}

    def flush() -> None:
        nonlocal body
        if current_num and current_title.lower() not in _SKIP_RFC:
            section_text = "\n".join(body).strip()
            section_text = re.sub(r"\n{3,}", "\n\n", section_text)
            if len(section_text) >= min_section_chars:
                if len(section_text) > max_section_chars:
                    chunks = _split_text_blocks(section_text, max_section_chars)
                    for part, chunk in enumerate(chunks, start=1):
                        sections.append(
                            TextSection(
                                heading=(
                                    f"RFC {number} §{current_num} {current_title}"
                                    + (f" (part {part})" if len(chunks) > 1 else "")
                                ),
                                body=chunk,
                                path=str(file_path),
                                metadata=dict(metadata),
                            )
                        )
                else:
                    sections.append(
                        TextSection(
                            heading=f"RFC {number} §{current_num} {current_title}".strip(),
                            body=section_text,
                            path=str(file_path),
                            metadata=dict(metadata),
                        )
                    )
        body = []

    for line in lines:
        if not line.startswith((" ", "\t")) and line.strip().lower() in _UNNUMBERED_SKIP:
            flush()
            current_num = ""
            current_title = ""
            continue
        match = _RFC_HEADING_RE.match(line)
        if match:
            flush()
            current_num = match.group("num").rstrip(".")
            current_title = match.group("title").strip()
            body = []
            continue
        if current_num:
            body.append(line)
    flush()
    return RfcDocument(number=number, title=title, category=category, date=date, sections=sections)


def _split_preserving_fences(text: str, max_chars: int) -> list[str]:
    """Split on paragraph boundaries while keeping fenced code blocks intact."""

    paragraphs: list[str] = []
    current: list[str] = []
    in_fence = False
    for line in text.split("\n"):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        if not in_fence and not line.strip():
            if current:
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
    return [chunk for chunk in chunks if chunk]


def _split_text_blocks(text: str, max_chars: int) -> list[str]:
    paragraphs: list[str] = []
    current: list[str] = []
    for line in text.split("\n"):
        if not line.strip() and current:
            paragraphs.append("\n".join(current).strip())
            current = []
        else:
            current.append(line)
    if current:
        paragraphs.append("\n".join(current).strip())
    chunks: list[str] = []
    buffer: list[str] = []
    size = 0
    for paragraph in paragraphs:
        if buffer and size + len(paragraph) > max_chars:
            chunks.append("\n\n".join(buffer).strip())
            buffer = []
            size = 0
        buffer.append(paragraph)
        size += len(paragraph) + 2
    if buffer:
        chunks.append("\n\n".join(buffer).strip())
    return [chunk for chunk in chunks if chunk]
