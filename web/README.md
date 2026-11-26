# CyberLite website

Static single-page research site for [CyberLite](../README.md).

No build step, no analytics, and no client-side framework. The page is one
`index.html`, a set of copied design-system assets under `assets/`, and the
paper PDF. Instrument Sans and DM Mono are loaded from Google Fonts with
`display=swap`; the Cloudflare headers allow only that stylesheet and its font
files.

```text
web/
├── index.html
├── share.jpg                 social card, a still of the hero
├── _headers                  security and cache headers for Cloudflare Pages
├── robots.txt
├── sitemap.xml
├── assets/
│   ├── system.css, system.js
│   ├── layout/               hero and section layout
│   ├── ui/                   window, document and code fragments
│   ├── motion/               hover, press and hero entrance
│   ├── backgrounds/          CSS ground tokens
│   ├── moments/              the one dealt marquee moment
│   ├── effects/              the dealt grain ground
│   ├── icons/                local tool marks and icon.css
│   ├── favicon.svg
│   └── cyberlite-paper.pdf   tracked snapshot of the compiled paper
└── README.md
```

The page uses the static kit copied from the `design-taste-frontend` skill. Do
not edit the kit files by hand to clear a check; change the page or report the
check.

## Preview

Open `index.html` directly in a browser, or serve the folder locally:

```bash
npx --yes serve web
# or: python -m http.server 8000 --directory web
```

`web/.taste-skill/` holds local QA notes and gate records from the design
check. It is ignored by Git and is not part of the site; exclude it when
uploading the folder manually.

## Paper PDF

`assets/cyberlite-paper.pdf` is a tracked snapshot of the compiled paper. The
repository ignores `paper/*.pdf`, so GitHub does not serve the generated PDF
directly. Refresh the snapshot after rebuilding the paper:

```bash
cp ../paper/main.pdf assets/cyberlite-paper.pdf
```

## Deploy with Cloudflare Pages

The site is static: no build step and no dependencies. There are two supported
ways to publish it.

### Git-connected Pages (recommended)

1. In the Cloudflare dashboard, go to **Workers & Pages** → **Create** →
   **Pages** → **Connect to Git**, and select this repository.
2. Use these build settings:
   - **Framework preset:** None
   - **Build command:** leave blank (or `exit 0`)
   - **Build output directory:** `web`
   - **Root directory:** repository root
3. Add this build environment variable for both production and preview:
   - `SKIP_DEPENDENCY_INSTALL=1`

   This stops Pages from installing the Python training dependencies in the
   repository's `requirements.txt` (PyTorch and CUDA wheels) for a static site.
4. Save and deploy. Pages uploads `web/` itself.

Do **not** add `npx wrangler pages deploy` as a deploy command in this project.
A Git-connected Pages project deploys its output directory automatically.

If the project settings show a **Deploy command** field, it is a Workers Builds
project rather than a Pages project. A `wrangler pages deploy` command there
needs a build token with **Account → Cloudflare Pages → Edit**; without it the
build ends with `Authentication error [code: 10000]`. For a static site, prefer
creating a Pages project instead. A build log that says
`Executing user deploy command` is Workers Builds, not Pages.

### Manual upload (optional)

Run these locally or in a CI job that has Cloudflare credentials. They are not
Cloudflare build settings.

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

### Domain and metadata

The page uses relative asset paths, so it works at a domain root or a subpath.
`_headers` adds security and cache headers on Cloudflare Pages and is ignored by
hosts that do not support it. Its content policy allows inline head scripts,
the Google Fonts stylesheet, and the font files; update it if the font source
changes. `robots.txt` and `sitemap.xml` assume the canonical host
`cyberlite.braydos.com`; update all three files, plus the `rel="canonical"`,
`og:url` and `og:image` values in `index.html`, if you deploy elsewhere.

To attach the domain, open the Pages project → **Custom domains** →
`cyberlite.braydos.com` and follow the DNS instructions.

## Keeping the page accurate

The project is a research preview. Three rules matter:

1. **Do not invent results.** The page quotes the E0 probe exactly: 23 of 24
   MCQ, classification accuracy 0.500, false-positive rate 1.000 on 12 items,
   25.25 s wall clock, 5.34 GB peak RSS. It labels the run a pipeline baseline,
   not a benchmark, and the paper's results tables stay pending until reviewed
   measurements exist.
2. **Keep progress in sync.** The page shows the 25 November 2026 snapshot:
   14 of 39 milestones (36%), Phase 0 at 10 of 10. After running
   `make progress` in the repository, update the matching figures in
   `index.html`: the E0 rows, the phase rows, the milestone heading and the
   snapshot date. Search for `14 of 39`, `10 of 10`, `25 November 2026`,
   `23 of 24`, `0.500` and `1.000`.
3. **Do not claim a checkpoint.** No trained research checkpoint or benchmark
   result is released. The hero, run report, safety section and close all say
   so; keep those limits in the copy.

## Content sources

- `README.md` — project overview, verified model facts, design table
- `GOALS.md` — goals and milestone counts
- `docs/roadmap.md` — roadmap phases
- `results/baseline/e0-instruct-probe/README.md` — the E0 run, probe data,
  hardware and throughput
- `configs/qlora.yaml` — the 6–8 GB starting configuration
- `docs/hardware.md` — VRAM classes and measurement protocol
- `docs/safety.md` — execution and evidence boundaries
- `paper/main.tex` — abstract and hypotheses

All outbound links point at <https://github.com/braydos-h/CyberLite> or the
tracked paper PDF. The only third-party requests are the Google Fonts files.
