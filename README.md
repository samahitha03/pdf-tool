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
- `static/vendor/` — pdf.js and anime.js, vendored locally so previews and
  animation work offline
- `run.sh` — launcher; creates `.venv` and installs deps on first run

## UI

The interface is animated with [anime.js](https://animejs.com/documentation/)
v4 (MIT, vendored as `static/vendor/anime.umd.min.js`, exposing the global
`anime`). It drives the intro timeline and logo line-drawing, the springy tab
indicator and panel cross-fades, staggered file-list and thumbnail entrances,
FLIP transitions when a page is deleted, the count-up on compression savings,
and the confetti particles.

Every animation goes through one `fx()` wrapper, so if anime.js fails to load
or the reader has `prefers-reduced-motion: reduce` set, each animation's end
state is applied immediately and the app stays fully usable.
