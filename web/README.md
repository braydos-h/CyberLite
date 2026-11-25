# CyberLite website

Static single-page research site for [CyberLite](../README.md).

No build step, no dependencies, and no external fonts or analytics. Everything
needed to render the page is in this folder.

```text
web/
├── index.html
├── assets/
│   ├── styles.css
│   ├── main.js
│   ├── favicon.svg
│   └── cyberlite-paper.pdf
└── README.md
```

## Preview

Open `index.html` directly in a browser, or drop the folder on any static host.

## Paper PDF

`assets/cyberlite-paper.pdf` is a tracked snapshot of the compiled paper. The
repository ignores `paper/*.pdf`, so GitHub does not serve the generated PDF
directly. Refresh the snapshot after rebuilding the paper:

```bash
cp ../paper/main.pdf assets/cyberlite-paper.pdf
```

## Deploy to Cloudflare Pages

- **Build command:** none
- **Build output directory:** `web`

The page uses relative asset paths, so it works at a domain root or a subpath.
If you deploy at a hostname other than `cyberlite.braydos.com`, update the
`rel="canonical"` and `og:url` values in `index.html`.

For a Git-connected Cloudflare Pages project, use the repository root as the
project root and `web` as the build output directory. For Direct Upload, use
this folder as the upload root.

## Keeping the page accurate

The project is a research preview. Two rules matter:

1. **Do not invent results.** The benchmark table intentionally stays blank and
   marked pending until a reviewed measurement exists.
2. **Keep progress in sync.** The milestone counts are a static snapshot of
   `GOALS.md` and `docs/roadmap.md` (25 November 2026, 14/39 milestones). After
   running `make progress` in the repository, update the matching numbers in
   `index.html`:
   - hero status card (`14 / 39 · 36%`)
   - overall progress card
   - six goal bars (G1–G6)
   - seven roadmap phase bars
   - the footer snapshot date

Search `index.html` for `36%`, `43%`, `25 Nov`, and `Snapshot` to find them.

## Content sources

- `README.md` — project overview, verified model facts, design table
- `GOALS.md` — goals and milestone counts
- `docs/roadmap.md` — roadmap phases
- `paper/main.tex` — abstract and hypotheses
- `docs/{evaluation,hardware,autocomplete,safety,limitations}.md` — benchmark,
  hardware, autocomplete, and safety details

All outbound links point at <https://github.com/braydos-h/CyberLite>.
