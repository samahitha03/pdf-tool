# Design notes

How the interface and the server are put together, for anyone changing them.
For installing and using the tool, see the [README](../README.md).

## Sessions


The loopback address is shared with every other process on the machine and
with every page open in the browser, so the server answers only requests that
clear three checks: the `Host` must be its own (which defeats DNS rebinding),
the `Origin`, when present, must be its own (which defeats cross-site posts),
and the request must carry this run's key.

The key is generated fresh at every launch and kept only in memory — never
written to a file, never printed into `server.log`. The tab that the launcher
opens is handed the key in its URL, trades it for a session cookie, and is
redirected to a clean address, so the key never sits in your address bar or
history.

In practice: open the tool from `run.sh` or `pdftool`, not from a bookmark.
A tab kept open across a restart, or a browser reopened after quitting, will
show a page saying it has no key — the fix is always:

```bash
pdftool stop && pdftool
```

If the browser does not open by itself, `run.sh` prints a link containing the
key (to the terminal only).

## Interface

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

## Motion

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

## Logging

Werkzeug's access log is one line per asset fetch and per
heartbeat, which buries anything worth reading, so it is turned down to
warnings and the app logs its own operations instead. A `@logged` decorator
wraps each API endpoint and derives everything from the request and response —
files in, filename and size out, duration, options, and the rejection reason on
a 4xx — so the handler bodies are untouched by it. Entries go to an in-memory
ring buffer (500) that the Activity view reads via `/api/logs?since=<cursor>`,
and are appended to `server.log` in a plain, ANSI-free format that survives a
restart. A log that cannot be written is swallowed: logging must never break the
tool.
