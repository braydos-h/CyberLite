# CyberLite website

Static single-page research site for [CyberLite](../README.md).

No build step, no dependencies, and no external fonts or analytics. Everything
needed to render the page is in this folder.

```text
web/
├── index.html
├── _headers
├── robots.txt
├── sitemap.xml
├── assets/
│   ├── styles.css
│   ├── main.js
│   ├── favicon.svg
│   └── cyberlite-paper.pdf
└── README.md
```

## Preview

Open `index.html` directly in a browser, or serve the folder locally:

```bash
npx --yes serve web
# or: python -m http.server 8000 --directory web
```

## Paper PDF

`assets/cyberlite-paper.pdf` is a tracked snapshot of the compiled paper. The
repository ignores `paper/*.pdf`, so GitHub does not serve the generated PDF
directly. Refresh the snapshot after rebuilding the paper:

```bash
cp ../paper/main.pdf assets/cyberlite-paper.pdf
```

## Deploy with npx (Cloudflare Pages)

The site is static: build command **none**, output directory **`web`**. Nothing
in the repository needs to be compiled before deployment.

One-time setup on a machine with a browser:

```bash
npx --yes wrangler@latest login
npx --yes wrangler@latest pages project create cyberlite --production-branch main
```

Deploy the current `web/` folder to production:

```bash
npx --yes wrangler@latest pages deploy web --project-name cyberlite --branch main
```

The same command is available as `make deploy-web`. Omit `--branch main` to
upload a preview deployment instead of production.

For CI or another headless environment, set a token with **Cloudflare Pages:
Edit** permission and the account ID:

```bash
CLOUDFLARE_API_TOKEN=... CLOUDFLARE_ACCOUNT_ID=... \
  npx --yes wrangler@latest pages deploy web --project-name cyberlite --branch main
```

No Cloudflare credentials are stored in this repository, and deployment is not
run by GitHub Actions.

The page uses relative asset paths, so it works at a domain root or a subpath.
`_headers` adds security and cache headers on Cloudflare Pages and is ignored by
hosts that do not support it. `robots.txt` and `sitemap.xml` assume the
canonical host `cyberlite.braydos.com`; update all three files, plus the
`rel="canonical"` and `og:url` values in `index.html`, if you deploy elsewhere.

To attach the domain, open the Pages project → **Custom domains** →
`cyberlite.braydos.com` and follow the DNS instructions. For a Git-connected
Pages project instead of the npx upload, use the repository root as the project
root and `web` as the build output directory.

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
