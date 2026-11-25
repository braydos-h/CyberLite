# CyberLite paper

This directory contains a LaTeX scaffold for:

> CyberLite: Resource-Efficient Post-Training of Sub-Billion-Parameter Language
> Models for Cybersecurity and Context-Aware Autocompletion

## Status

The paper is a **work in progress**. Hypotheses and protocols are specified;
performance tables are explicit placeholders. No benchmark result is reported.

## Build

```bash
cd paper
latexmk -pdf main.tex
```

or with Tectonic:

```bash
tectonic main.tex
```

The GitHub Actions workflow `paper.yml` compiles the PDF on changes.

## Structure

- `main.tex` — preamble, title, abstract, section inputs, bibliography
- `sections/` — one file per major section
- `references.bib` — verified references; no invented citations
- `figures/` — add generated figures here (the current pipeline diagram is TikZ)

## Before submission

- Replace every `\pending{}` with a reviewed measurement or remove the row.
- Freeze the dataset and evaluation versions.
- Add author affiliations and acknowledgements.
- Check the venue's anonymity, page limit, and artifact policy.
- Verify every citation against the published record.
