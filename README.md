# PDF Tool (local)

A small local web app to merge, split and organize PDFs, and convert
JPG/PNG images to PDF. Everything runs on your machine — files are
processed in memory and never leave your computer.

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

## Files

- `app.py` — Flask server (`/api/merge`, `/api/split`, `/api/organize`, `/api/jpg-to-pdf`)
- `static/index.html` — the UI (single file, no build step)
- `static/vendor/` — pdf.js, vendored locally so page previews work offline
- `run.sh` — launcher; creates `.venv` and installs deps on first run
