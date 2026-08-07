# PDF Tool (local)

A small local web app to merge, split, organize and compress PDFs,
convert JPG/PNG images to PDF, and compress images. Everything runs on
your machine — files are processed in memory and never leave your computer.

## Start

```bash
~/Documents/pdf-tool/run.sh
```

The first run sets up a Python virtual environment (one time, ~30s).
Your browser opens automatically at http://127.0.0.1:5177.
Press `Ctrl+C` in the terminal to stop.

## Features

- **Merge** — drop two or more PDFs, drag them into the order you want,
  name the output, click Merge. The result downloads via your browser.
- **Split** — drop one PDF, then either extract pages (`1-3, 5, 8-`) into
  a single new PDF, split by ranges into separate PDFs (ZIP), or save
  every page as its own PDF (ZIP).
- **Organize** — drop one PDF and work with live page thumbnails:
  drag to reorder, rotate pages in 90° steps, remove pages, then
  download the rebuilt PDF.
- **Images to PDF** — drop one or more JPG/PNG images (each becomes a
  page), reorder by dragging, pick a page size (fit-to-image, A4, or
  Letter), click Convert.
- **Compress** — drop one PDF or JPG/PNG image and shrink it.
  Presets: *Less Compression* (high quality), *Recommended* (good
  quality and compression, default), *Extreme* (smallest files). Or
  pick a *Custom target*: reduce by 25%, 50%, 75%, or any ratio via
  the slider — a bounded quality search hits the target with
  consistent speed. Images come back as JPG. If a file can't be made
  smaller, the original is returned unchanged.

After every successful operation the upload area clears automatically,
ready for the next job.

## Files

- `app.py` — Flask server (`/api/merge`, `/api/split`, `/api/organize`, `/api/jpg-to-pdf`, `/api/compress`)
- `static/index.html` — the UI (single file, no build step)
- `static/icon.svg` — the app mark; `static/favicon.svg` — a simplified cut of
  the same artwork for the browser tab
- `static/vendor/` — pdf.js, anime.js and three webfonts, vendored locally so
  previews, animation and typography all work offline
- `run.sh` — launcher; creates `.venv` and installs deps on first run

## UI

The Bitcoin DeFi aesthetic: a true-void ground with Bitcoin-fire energy. All
tokens are custom properties at the top of `static/index.html`; there is no
build step and no utility-class framework.

**Dark only, by design.** The glow, the glass and the fading grid all depend on
darkness to read at all, so there is no light register and `prefers-color-scheme`
is deliberately ignored. `<meta name="color-scheme" content="dark">` tells the
browser to match.

**Tokens.** `--void` `#030304` is the ground and `--surface` `#0F1115` the
elevated panels. `--orange` `#F7931A` is the primary accent, `--burnt` `#EA580C`
its gradient partner, and `--gold` `#FFD600` marks value — used on the
compression-savings readout and the progress bar. `--fire` and `--value` are the
two signature gradients. Every shadow in the file is a coloured glow; there are
no black shadows.

**Type carries meaning.** Space Grotesk sets headings, Inter sets body copy, and
JetBrains Mono is reserved for *data* — file sizes, page counts, percentages,
the tab register and every uppercase label. That split is functional, not
decorative: anything the user reads as a measurement is monospaced. All three
are OFL, vendored as variable woff2, 102KB total, no CDN request.

**Vocabulary.** Pill-shaped buttons and tab indicator; glass-morphic tab bar
over the void; 1px `white/10` borders that shift to orange on hover; rounded-2xl
panels with orange corner accents; "holographic node" badges for row numbers;
bottom-border-only inputs over `black/50`; a 50px grid masked to a radial
vignette; drifting radial energy fields; counter-rotating orbital rings around
the mark; and a live-network ping on the trust badge.

**One deliberate departure.** The system specifies white text on the
`#EA580C → #F7931A` button gradient. Measured, that is 3.56:1 and 2.30:1 — both
under the 4.5:1 AA floor at this text size. Near-void ink (`--on-fire`) gets
5.67:1 and 8.79:1 on the same two stops, so every surface filled with the fire
gradient uses dark ink instead. The look is unchanged; only the label flips.

**The app mark** is vector, not raster. `icon.svg` carries the full artwork —
violet folder, document sheet, ember card and a pixel-dissolve trail — and
`favicon.svg` is a simplified cut of it: bolder shapes, no ruled lines, three
embers instead of eighteen. Detail that reads at 512px turns to mush at 16px,
so the tab icon deliberately carries less. Being SVG, both stay sharp at any
size and add no binary asset or extra request. The mark keeps its own violet
identity rather than being retuned to the Bitcoin-fire palette.

The interface is animated with [anime.js](https://animejs.com/documentation/)
v4 (MIT, vendored as `static/vendor/anime.umd.min.js`, exposing the global
`anime`). It drives the intro timeline and mark line-drawing, the tab indicator
and panel cross-fades, staggered file-list and thumbnail entrances, FLIP
transitions when a page is deleted, the count-up on compression savings, the
ambient orbitals and energy fields, and the confetti. DeFi motion is snappy —
fast interaction easing over slow ambient loops.

Every animation goes through one `fx()` wrapper, so if anime.js fails to load
or the reader has `prefers-reduced-motion: reduce` set, each animation's end
state is applied immediately and the app stays fully usable. This means **CSS
must always hold an animation's end state** — `clean()` reverts inline styles
back to the stylesheet, so any resting value that only an animation sets will
silently collapse when that animation finishes.
