from __future__ import annotations

from pathlib import Path

from cyberlite.data.textdocs import parse_rfc, parse_roff


def test_roff_sections_and_spdx_license(tmp_path: Path) -> None:
    page = tmp_path / "chmod.2"
    page.write_text(
        """.\\" SPDX-License-Identifier: GPL-2.0-or-later
.TH chmod 2 2024-06-13 "Linux man-pages"
.SH NAME
chmod \\- change permissions
.SH DESCRIPTION
The chmod() call changes the mode bits of a file.
.PP
Use the least privilege necessary for the service account.
.SS Special bits
Set-user-ID and set-group-ID bits require additional review.
.SH EXAMPLES
.nf
chmod 750 /srv/app
.fi
.SH COPYRIGHT
Copyright 2024 Example.
""",
        encoding="utf-8",
    )
    document = parse_roff(page, min_section_chars=20)
    assert document.title == "chmod"
    assert document.section == "2"
    assert document.spdx_license == "GPL-2.0-or-later"
    headings = [section.heading for section in document.sections]
    assert "DESCRIPTION" in headings
    assert "DESCRIPTION — Special bits" in headings
    assert "EXAMPLES" in headings
    examples = next(section for section in document.sections if section.heading == "EXAMPLES")
    assert "```" in examples.body
    assert "chmod 750" in examples.body
    assert not any("COPYRIGHT" in heading for heading in headings)


def test_rfc_sections_remove_page_artifacts(tmp_path: Path) -> None:
    rfc = tmp_path / "rfc9999.txt"
    rfc.write_text(
        """
Internet Engineering Task Force (IETF)                       A. Author
Request for Comments: 9999                                      Example
Category: Informational                                        August 2024


                     A Small Networking Example

Abstract

   This is the abstract and should not become a training section.

1.  Introduction

   This section explains the operational security context of the protocol and
   the assumptions a defender should verify before deployment.

Rescorla                     Informational                     [Page 1]

RFC 9999                       Example                       August 2024


1.1.  Threat Model

   The threat model covers an on-path attacker and a compromised endpoint.
   Mitigations must be validated in the deployment context.

Authors' Addresses

   Example Author
   example@example.invalid
""",
        encoding="utf-8",
    )
    document = parse_rfc(rfc, min_section_chars=50)
    assert document.number == "9999"
    headings = [section.heading for section in document.sections]
    assert any("Introduction" in heading for heading in headings)
    assert any("Threat Model" in heading for heading in headings)
    assert not any("Authors' Addresses" in heading for heading in headings)
    body = "\n".join(section.body for section in document.sections)
    assert "[Page 1]" not in body
    assert "example@example.invalid" not in body


def test_roff_long_section_splits_without_duplicating_text(tmp_path: Path) -> None:
    page = tmp_path / "long.5"
    paragraphs = "\n.PP\n".join(
        f"Paragraph {index} explains a distinct kernel parameter and its defensive default."
        for index in range(200)
    )
    page.write_text(
        f".TH long 5\n.SH DESCRIPTION\n{paragraphs}\n",
        encoding="utf-8",
    )
    document = parse_roff(page, min_section_chars=20, max_section_chars=800)
    assert len(document.sections) > 1
    combined = "\n".join(section.body for section in document.sections)
    assert combined.count("Paragraph 0 ") == 1
    assert len(combined) < 50_000


def test_mdoc_title_and_section(tmp_path: Path) -> None:
    page = tmp_path / "sshd_config.5"
    page.write_text(
        """.Dd $Mdocdate: September 17 2026 $
.Dt SSHD_CONFIG 5
.Os
.Sh NAME
.Nm sshd_config
.Nd configuration file for the OpenSSH daemon
.Sh DESCRIPTION
.It Cm PermitRootLogin
Specifies whether root can log in using ssh.
.It Cm PasswordAuthentication
Specifies whether password authentication is allowed.
""",
        encoding="utf-8",
    )
    document = parse_roff(page, min_section_chars=10)
    assert document.title == "SSHD_CONFIG"
    assert document.section == "5"
    assert any(section.heading == "DESCRIPTION" for section in document.sections)
    body = "\n".join(section.body for section in document.sections)
    assert "PermitRootLogin" in body
    assert "PasswordAuthentication" in body
