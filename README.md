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
- `static/vendor/` — pdf.js, anime.js and the two webfonts, vendored locally so
  previews, animation and typography all work offline
- `run.sh` — launcher; creates `.venv` and installs deps on first run

## UI

Art Deco, rendered in a four-tone palette: `#9CB080` sage, `#618764` moss,
`#2B5748` pine, `#273338` slate. All tokens are custom properties at the top of
`static/index.html`; there is no build step and no utility-class framework.

**Two registers.** Light and dark are not inversions of each other — they are
the two period-authentic Deco grounds. Dark is a ballroom: gilt ornament on a
near-obsidian slate. Light is a printed poster: deep green ink on champagne
paper. In each, the palette's most luminous tone plays the "gold" role that
carries every border, rule and heading — sage on the dark ground, pine on the
light one.

**Token roles.** `--accent` is the ornament colour, `--accent-bright` its
metallic highlight, `--on-accent` the ink that sits on a filled accent surface,
and `--rule`/`--rule-soft` the two weights of frame line. Splitting "colour that
must read as text" from "colour that must be readable *against*" is what keeps
both themes accessible from one set of variables — every text/background pair
clears its WCAG AA minimum in both.

**Deco vocabulary.** Sharp corners throughout (no radii); notched clip-paths on
filled elements and corner brackets on outlined ones; double frames on panels
and page thumbnails; a rotated-diamond crest and dropzone marks; Roman numerals
on the tab register and file list; all-caps display type with 0.2em tracking;
glows instead of drop shadows; and a backdrop of rotating sunburst rays,
diagonal crosshatch and film grain. Type is Marcellus (display) and Josefin Sans
(body), both OFL, vendored as woff2 — 43KB total, no CDN request.

Page thumbnails keep their double frame but **not** the design system's
default grayscale-until-hover treatment: these are previews the user is reading
to decide what to keep, so desaturating them would trade function for style.
Page numbers stay Arabic for the same reason — someone hunting for page 34
wants "34", not "XXXIV".

The interface is animated with [anime.js](https://animejs.com/documentation/)
v4 (MIT, vendored as `static/vendor/anime.umd.min.js`, exposing the global
`anime`). It drives the intro timeline and crest line-drawing, the tab
indicator and panel cross-fades, staggered file-list and thumbnail entrances,
FLIP transitions when a page is deleted, the count-up on compression savings,
and the confetti. Deco motion is mechanical rather than organic, so everything
uses fixed-duration eases — no springs, nothing that overshoots.

Every animation goes through one `fx()` wrapper, so if anime.js fails to load
or the reader has `prefers-reduced-motion: reduce` set, each animation's end
state is applied immediately and the app stays fully usable. This means **CSS
must always hold an animation's end state** — `clean()` reverts inline styles
back to the stylesheet, so any resting value that only an animation sets will
silently collapse when that animation finishes.
