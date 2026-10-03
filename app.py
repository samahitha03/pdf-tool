"""Local PDF Tool — merge, split, organize, unlock, compress PDFs and convert images to PDF.

Runs entirely on your machine. Start with ./run.sh and the UI opens
in your browser at http://127.0.0.1:5177
"""

import io
import json
import logging
import os
import secrets
import sys
import time
import threading
import webbrowser
import zipfile
from collections import deque
from functools import wraps
from threading import Timer

from flask import (Flask, jsonify, make_response, redirect, request, send_file,
                   send_from_directory)
from pypdf import PdfWriter, PdfReader, PasswordType
from pypdf.errors import DependencyError, FileNotDecryptedError
from PIL import Image

HOST = "127.0.0.1"
PORT = 5177
# Shut down after this many seconds with no open tabs (heartbeats)
IDLE_TIMEOUT = int(os.environ.get("PDF_TOOL_IDLE_TIMEOUT", "600"))
MAX_CONTENT_LENGTH = int(os.environ.get("PDF_TOOL_MAX_CONTENT_LENGTH", str(50 * 1024 * 1024)))

# Everything below exists because this server, though bound to the loopback
# address, is still reachable by every page in the browser and every process on
# the machine. A page on any site can post to it, a rebound DNS name can read
# from it, and any local process can drive it — unless the requests are checked.
ALLOWED_HOSTS = {f"{HOST}:{PORT}", f"localhost:{PORT}"}
ALLOWED_ORIGINS = {f"http://{HOST}:{PORT}", f"http://localhost:{PORT}"}
# One secret per launch, held in memory and never written anywhere: server.log
# is world-readable, so a token on disk would be worse than none at all.
SESSION_TOKEN = secrets.token_urlsafe(32)
COOKIE_NAME = "pdftool_session"
TOKEN_PARAM = "t"
TOKEN_HEADER = "X-PDF-Tool-Token"

HERE = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(HERE, "server.log")
LOG_MAX_BYTES = 1024 * 1024      # rotate to server.log.1 past this
LOG_BUFFER = 500                 # entries kept in memory for the Activity view

app = Flask(__name__, static_folder="static")
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

# Werkzeug's access log is one line per asset fetch and per heartbeat, which
# buries anything worth reading. Keep its warnings, drop the chatter, and log
# the operations we actually care about ourselves.
logging.getLogger("werkzeug").setLevel(logging.WARNING)

last_activity = time.time()

# ---------- activity log ----------

_log_lock = threading.Lock()
_log_entries = deque(maxlen=LOG_BUFFER)
_log_seq = 0

TOOL_LABELS = {
    "merge": "Merge", "split": "Split", "organize": "Organize",
    "jpg": "Images", "compress": "Compress", "unlock": "Unlock",
    "server": "Server",
}


def human_bytes(n):
    if n is None:
        return "?"
    if n > 1048576:
        return f"{n / 1048576:.1f} MB"
    if n > 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n} B"


def _rotate_log_if_large():
    try:
        if os.path.getsize(LOG_FILE) > LOG_MAX_BYTES:
            os.replace(LOG_FILE, LOG_FILE + ".1")
    except OSError:
        pass


def log_event(level, event, msg, **detail):
    """Record one activity entry: in memory for the UI, on disk to outlive it.

    level is one of info | ok | warn | error.
    """
    global _log_seq
    with _log_lock:
        _log_seq += 1
        entry = {
            "id": _log_seq,
            "ts": time.time(),
            "level": level,
            "event": event,
            "msg": msg,
            "detail": {k: v for k, v in detail.items() if v not in (None, "")},
        }
        _log_entries.append(entry)

        stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(entry["ts"]))
        line = f"{stamp}  {level:<5}  {event:<9} {msg}"
        if entry["detail"]:
            line += "  " + " ".join(f"{k}={v}" for k, v in entry["detail"].items())
        try:
            if _log_seq % 50 == 0:
                _rotate_log_if_large()
            with open(LOG_FILE, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except OSError:
            pass       # a log that cannot be written must never break the tool
    return entry


def logged(event):
    """Time an endpoint and record how it went.

    Everything worth logging — which files came in, what came out, how long it
    took, why it was rejected — is derivable from the request and the response,
    so the handlers themselves stay untouched.
    """
    def decorate(fn):
        @wraps(fn)
        def inner(*args, **kwargs):
            names = [f.filename for f in request.files.getlist("files") if f.filename]
            one = request.files.get("file")
            if one is not None and one.filename:
                names.append(one.filename)
            sent = request.content_length
            opts = {k: request.form.get(k) for k in ("mode", "ranges", "ratio", "page_size")
                    if request.form.get(k)}
            label = TOOL_LABELS.get(event, event)
            source = f"{len(names)} files" if len(names) > 3 else (", ".join(names) or "—")

            started = time.perf_counter()
            try:
                response = fn(*args, **kwargs)
            except Exception as exc:
                log_event("error", event, f"{label} failed: {exc}",
                          source=source, ms=round((time.perf_counter() - started) * 1000))
                raise
            ms = round((time.perf_counter() - started) * 1000)

            if isinstance(response, tuple):
                body, status = response[0], response[1]
            else:
                body, status = response, getattr(response, "status_code", 200)

            if status >= 400:
                reason = ""
                try:
                    reason = (body.get_json(silent=True) or {}).get("error", "")
                except Exception:
                    pass
                log_event("warn", event, reason or f"{label} rejected ({status})",
                          source=source, ms=ms, **opts)
            else:
                disposition = body.headers.get("Content-Disposition", "") if hasattr(body, "headers") else ""
                out = ""
                if "filename=" in disposition:
                    out = disposition.split("filename=", 1)[1].strip('"; ')
                got = getattr(body, "content_length", None)
                log_event("ok", event, f"{label}: {source} → {out or 'output'}",
                          size=f"{human_bytes(sent)} → {human_bytes(got)}", ms=ms, **opts)
            return response
        return inner
    return decorate


# ---------- access control ----------

DENIED_PAGE = """<!doctype html>
<meta charset="utf-8"><title>PDF Tool — session needed</title>
<style>
  body {{ background:#030304; color:#e9edf2; font:16px/1.7 -apple-system,system-ui,sans-serif;
         display:grid; place-items:center; min-height:100vh; margin:0; text-align:center }}
  div {{ max-width:34rem; padding:2rem }}
  h1 {{ font-size:1.3rem; margin:0 0 .8rem }}
  code {{ background:#14161c; padding:.2em .5em; border-radius:6px; color:#f7931a }}
  p {{ color:#98a2b3 }}
</style>
<div>
  <h1>This tab isn't signed in to PDF Tool</h1>
  <p>{reason}</p>
  <p>The tool hands its browser tab a key when it starts, and that key lasts
     only as long as this run. Open it again from the launcher:</p>
  <p><code>pdftool stop &amp;&amp; pdftool</code></p>
</div>
"""

_denial_log = {}          # reason → when it was last written, to cap log noise


def _deny(reason, status=403):
    """Refuse a request, logging each distinct reason at most once per 10s.

    Without the throttle a hostile page could fill server.log by looping.
    """
    now = time.time()
    if now - _denial_log.get(reason, 0) > 10:
        _denial_log[reason] = now
        log_event("warn", "server", f"Blocked a request: {reason}", path=request.path)
    if request.path.startswith("/api/"):
        return jsonify(error=f"{reason}. Restart the tool with: pdftool stop && pdftool"), status
    return DENIED_PAGE.format(reason=reason), status, {"Content-Type": "text/html; charset=utf-8"}


def _token_ok(supplied):
    return supplied is not None and secrets.compare_digest(supplied, SESSION_TOKEN)


@app.before_request
def guard_request():
    """Answer only this machine's browser, running this launch of the tool.

    Three separate doors, because they stop three different things: the Host
    check defeats DNS rebinding, the Origin check defeats cross-site posts, and
    the token keeps other local processes — which share the loopback address —
    out of the API and the activity log.
    """
    if request.host not in ALLOWED_HOSTS:
        return _deny("that host name is not this tool's own")

    origin = request.headers.get("Origin")
    if origin and origin not in ALLOWED_ORIGINS:
        return _deny("that request came from another site")

    if request.headers.get("Sec-Fetch-Site") in ("cross-site", "same-site"):
        return _deny("that request came from another site")

    # Vendored scripts, fonts and the app mark: public files, no user data.
    # /favicon.ico is here because browsers probe it on their own, outside the
    # page's cookie context — refusing it would log a scare on every load.
    if request.path.startswith("/static/") or request.path == "/favicon.ico":
        return None

    if _token_ok(request.cookies.get(COOKIE_NAME)) or \
            _token_ok(request.headers.get(TOKEN_HEADER)):
        return None

    # The launcher opens /?t=<token>. Trade it for a cookie and redirect to a
    # clean URL, so the key never lingers in the address bar or in history.
    if request.path == "/" and _token_ok(request.args.get(TOKEN_PARAM)):
        response = make_response(redirect("/", code=302))
        response.set_cookie(COOKIE_NAME, SESSION_TOKEN, httponly=True,
                            samesite="Strict", path="/")
        return response

    return _deny("this tab has no key for the running tool")


@app.before_request
def touch_activity():
    global last_activity
    last_activity = time.time()


@app.post("/api/heartbeat")
def heartbeat():
    return jsonify(ok=True)


@app.get("/api/logs")
def read_logs():
    """Entries newer than `since`. Not itself logged — it would never stop."""
    try:
        since = int(request.args.get("since", "0"))
    except ValueError:
        since = 0
    with _log_lock:
        return jsonify(entries=[e for e in _log_entries if e["id"] > since],
                       cursor=_log_seq)


@app.post("/api/logs/clear")
def clear_logs():
    """Empties the in-memory view. server.log on disk is left intact."""
    with _log_lock:
        _log_entries.clear()
    log_event("info", "server", "Activity view cleared (server.log kept)")
    return jsonify(ok=True)


def idle_watchdog():
    while True:
        time.sleep(min(30, IDLE_TIMEOUT / 2))
        if time.time() - last_activity > IDLE_TIMEOUT:
            log_event("warn", "server", f"No activity for {IDLE_TIMEOUT}s — shutting down")
            print(f"No activity for {IDLE_TIMEOUT}s — shutting down.")
            os._exit(0)

# A4 and Letter sizes in PDF points (72 pt per inch)
PAGE_SIZES = {
    "a4": (595.0, 842.0),
    "letter": (612.0, 792.0),
}


@app.get("/favicon.ico")
def favicon():
    """Browsers ask for this by convention even though the page names the SVG."""
    return send_from_directory("static", "favicon.svg")


@app.get("/")
def index():
    return send_from_directory("static", "index.html")


class PdfToolError(ValueError):
    """A user-facing error (bad input, unreadable file)."""


def read_pdf(f):
    reader = PdfReader(io.BytesIO(f.read()))
    if reader.is_encrypted:
        # An empty password opens files that carry only restrictions; anything
        # else belongs in the Unlock tab, where a password can be given.
        try:
            opened = reader.decrypt("")
        except Exception:
            opened = PasswordType.NOT_DECRYPTED
        if opened == PasswordType.NOT_DECRYPTED:
            raise PdfToolError(
                f"'{f.filename}' is password-protected — remove its password "
                "in the Unlock tab first.")
    return reader


def output_name(default, suffix=".pdf"):
    name = os.path.basename(request.form.get("output_name", "").strip()) or default
    if not name.lower().endswith(suffix):
        name += suffix
    return name


def pdf_response(writer, name):
    out = io.BytesIO()
    writer.write(out)
    out.seek(0)
    return send_file(out, mimetype="application/pdf",
                     as_attachment=True, download_name=name)


def parse_ranges(spec, page_count):
    """Parse '1-3, 5, 8-' into a list of 1-indexed (start, end) tuples."""
    ranges = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            if "-" in part:
                a, _, b = part.partition("-")
                start = int(a) if a.strip() else 1
                end = int(b) if b.strip() else page_count
            else:
                start = end = int(part)
        except ValueError:
            raise PdfToolError(f"'{part}' is not a valid page range.")
        if start < 1 or end > page_count or start > end:
            raise PdfToolError(
                f"Range '{part}' is out of bounds — this PDF has {page_count} page(s).")
        ranges.append((start, end))
    if not ranges:
        raise PdfToolError("Enter at least one page or range, e.g. 1-3, 5.")
    return ranges


@app.post("/api/merge")
@logged("merge")
def merge_pdfs():
    files = request.files.getlist("files")
    if len(files) < 2:
        return jsonify(error="Upload at least two PDF files to merge."), 400

    writer = PdfWriter()
    try:
        for f in files:
            reader = read_pdf(f)
            for page in reader.pages:
                writer.add_page(page)
    except PdfToolError as e:
        return jsonify(error=str(e)), 400
    except Exception as e:
        return jsonify(error=f"Could not read '{f.filename}': {e}"), 400

    return pdf_response(writer, output_name("merged"))


@app.post("/api/split")
@logged("split")
def split_pdf():
    f = request.files.get("file")
    if not f:
        return jsonify(error="Upload a PDF to split."), 400

    mode = request.form.get("mode", "extract")  # extract | separate | every
    try:
        reader = read_pdf(f)
        n = len(reader.pages)
        if mode == "every":
            ranges = [(i, i) for i in range(1, n + 1)]
        else:
            ranges = parse_ranges(request.form.get("ranges", ""), n)
    except PdfToolError as e:
        return jsonify(error=str(e)), 400
    except Exception as e:
        return jsonify(error=f"Could not read '{f.filename}': {e}"), 400

    stem = os.path.splitext(os.path.basename(f.filename or "document"))[0]

    if mode == "extract":
        writer = PdfWriter()
        for start, end in ranges:
            for i in range(start - 1, end):
                writer.add_page(reader.pages[i])
        return pdf_response(writer, output_name(f"{stem}_extracted"))

    # separate / every → one PDF per range, zipped
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for start, end in ranges:
            writer = PdfWriter()
            for i in range(start - 1, end):
                writer.add_page(reader.pages[i])
            part = io.BytesIO()
            writer.write(part)
            label = f"page_{start}" if start == end else f"pages_{start}-{end}"
            zf.writestr(f"{stem}_{label}.pdf", part.getvalue())
    buf.seek(0)
    return send_file(buf, mimetype="application/zip", as_attachment=True,
                     download_name=output_name(f"{stem}_split", ".zip"))


@app.post("/api/organize")
@logged("organize")
def organize_pdf():
    f = request.files.get("file")
    if not f:
        return jsonify(error="Upload a PDF to organize."), 400

    try:
        pages = json.loads(request.form.get("pages", "[]"))
        if not isinstance(pages, list) or not pages:
            raise PdfToolError("Keep at least one page.")
        reader = read_pdf(f)
        n = len(reader.pages)
        writer = PdfWriter()
        for spec in pages:
            idx = int(spec.get("index", -1))
            rot = int(spec.get("rotate", 0)) % 360
            if not 0 <= idx < n:
                raise PdfToolError(f"Page index {idx + 1} is out of bounds.")
            if rot not in (0, 90, 180, 270):
                raise PdfToolError("Rotation must be 0, 90, 180 or 270 degrees.")
            page = reader.pages[idx]
            if rot:
                page.rotate(rot)
            writer.add_page(page)
    except PdfToolError as e:
        return jsonify(error=str(e)), 400
    except Exception as e:
        return jsonify(error=f"Could not organize '{f.filename}': {e}"), 400

    stem = os.path.splitext(os.path.basename(f.filename or "document"))[0]
    return pdf_response(writer, output_name(f"{stem}_organized"))


@app.post("/api/jpg-to-pdf")
@logged("jpg")
def jpg_to_pdf():
    files = request.files.getlist("files")
    if not files:
        return jsonify(error="Upload at least one image."), 400

    page_size = request.form.get("page_size", "fit")  # fit | a4 | letter
    pages = []
    try:
        for f in files:
            img = Image.open(io.BytesIO(f.read()))
            if img.mode in ("RGBA", "P", "LA"):
                img = img.convert("RGB")
            elif img.mode != "RGB":
                img = img.convert("RGB")

            if page_size == "fit":
                pages.append(img)
            else:
                pw, ph = PAGE_SIZES[page_size]
                # Render at 150 dpi equivalent for a crisp page
                scale = 150 / 72
                canvas_w, canvas_h = int(pw * scale), int(ph * scale)
                canvas = Image.new("RGB", (canvas_w, canvas_h), "white")
                ratio = min((canvas_w * 0.92) / img.width,
                            (canvas_h * 0.92) / img.height)
                new_size = (int(img.width * ratio), int(img.height * ratio))
                img = img.resize(new_size, Image.LANCZOS)
                canvas.paste(img, ((canvas_w - new_size[0]) // 2,
                                   (canvas_h - new_size[1]) // 2))
                pages.append(canvas)
    except Exception as e:
        return jsonify(error=f"Could not read image '{f.filename}': {e}"), 400

    out = io.BytesIO()
    pages[0].save(out, format="PDF", save_all=True, append_images=pages[1:],
                  resolution=150 if page_size != "fit" else 72)
    out.seek(0)
    name = request.form.get("output_name", "").strip() or "images"
    name = os.path.basename(name)
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    return send_file(out, mimetype="application/pdf",
                     as_attachment=True, download_name=name)


# ---------- compression ----------

# Preset → JPEG quality + max image dimension (0 = keep original resolution)
COMPRESS_PRESETS = {
    "extreme":     {"quality": 30, "max_dim": 1200},  # smallest files
    "recommended": {"quality": 60, "max_dim": 1800},  # good balance
    "less":        {"quality": 85, "max_dim": 0},     # best quality
}
# Quality/downscale rungs used to hit a target ratio, mildest first.
# Bisecting this ladder caps PDF rebuilds at 3, so speed stays consistent.
RATIO_LADDER = [(90, 0), (75, 2200), (60, 1800), (45, 1400),
                (30, 1100), (15, 850), (8, 650)]


def flatten_rgb(img):
    """RGB copy of an image; transparency is composited over white."""
    if img.mode in ("RGBA", "LA", "PA") or \
            (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        bg = Image.new("RGB", rgba.size, "white")
        bg.paste(rgba, mask=rgba.split()[-1])
        return bg
    return img if img.mode == "RGB" else img.convert("RGB")


def downscaled(img, max_dim):
    if max_dim and max(img.size) > max_dim:
        img = img.copy()
        img.thumbnail((max_dim, max_dim), Image.LANCZOS)
    return img


def jpeg_bytes(img, quality):
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality, optimize=True, progressive=True)
    return buf.getvalue()


def best_quality_under(img, target):
    """Highest-quality JPEG of img that fits in target bytes (None if q=5 doesn't)."""
    lo, hi, best = 5, 95, None
    while lo <= hi:  # ≤7 encodes
        q = (lo + hi) // 2
        out = jpeg_bytes(img, q)
        if len(out) <= target:
            best, lo = out, q + 1
        else:
            hi = q - 1
    return best


def compress_image(data, mode, ratio):
    img = flatten_rgb(Image.open(io.BytesIO(data)))
    if mode != "ratio":
        p = COMPRESS_PRESETS[mode]
        return jpeg_bytes(downscaled(img, p["max_dim"]), p["quality"])

    target = len(data) * (1 - ratio)
    best = best_quality_under(img, target)
    if best is not None:
        return best
    # Even quality 5 is too big — downscale toward the target and retry once.
    floor = jpeg_bytes(img, 5)
    scale = max(0.2, (target / len(floor)) ** 0.5)
    img = img.resize((max(1, int(img.width * scale)),
                      max(1, int(img.height * scale))), Image.LANCZOS)
    return best_quality_under(img, target) or jpeg_bytes(img, 5)


def rebuild_pdf(data, quality, max_dim):
    """Rewrite a PDF with its embedded images re-encoded at the given quality."""
    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted:
        try:
            opened = reader.decrypt("")
        except Exception:
            opened = PasswordType.NOT_DECRYPTED
        if opened == PasswordType.NOT_DECRYPTED:
            raise PdfToolError("This PDF is password-protected — remove its "
                               "password in the Unlock tab first.")
    writer = PdfWriter(clone_from=reader)
    for page in writer.pages:
        for img in page.images:
            try:
                pil = img.image
                if pil is None:
                    continue
                img.replace(downscaled(flatten_rgb(pil), max_dim),
                            quality=quality)
            except Exception:
                continue  # leave images pypdf can't rewrite untouched
        try:
            page.compress_content_streams(level=9)
        except Exception:
            pass
    try:
        writer.compress_identical_objects(remove_identicals=True,
                                          remove_orphans=True)
    except Exception:
        pass
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def compress_pdf(data, mode, ratio):
    if mode != "ratio":
        p = COMPRESS_PRESETS[mode]
        return rebuild_pdf(data, p["quality"], p["max_dim"])

    target = len(data) * (1 - ratio)
    lo, hi, best, best_idx = 0, len(RATIO_LADDER) - 1, None, None
    while lo <= hi:  # bisect the ladder: ≤3 rebuilds
        mid = (lo + hi) // 2
        out = rebuild_pdf(data, *RATIO_LADDER[mid])
        if len(out) <= target:
            best, best_idx, hi = out, mid, mid - 1  # target met — try milder
        else:
            lo = mid + 1                            # need stronger compression
    if best is None:
        # No rung met the target; the loop ends on the strongest one.
        return out
    if best_idx > 0:
        # One refinement between the winning rung and its milder neighbour
        # keeps quality as high as the target allows (≤4 rebuilds total).
        q_mild, dim_mild = RATIO_LADDER[best_idx - 1]
        q_won = RATIO_LADDER[best_idx][0]
        refined = rebuild_pdf(data, (q_mild + q_won) // 2, dim_mild)
        if len(refined) <= target:
            return refined
    return best


@app.post("/api/compress")
@logged("compress")
def compress_file():
    files = request.files.getlist("files")
    if not files:
        return jsonify(error="Upload a PDF or image to compress."), 400
    if len(files) > 1:
        return jsonify(error="Compress one file at a time."), 400

    mode = request.form.get("mode", "recommended")
    if mode != "ratio" and mode not in COMPRESS_PRESETS:
        return jsonify(error="Unknown compression mode."), 400
    ratio = 0.5
    if mode == "ratio":
        try:
            pct = int(request.form.get("ratio", "50"))
        except ValueError:
            return jsonify(error="Reduction must be a number."), 400
        if not 5 <= pct <= 90:
            return jsonify(error="Reduction must be between 5% and 90%."), 400
        ratio = pct / 100

    f = files[0]
    data = f.read()
    name = os.path.basename(f.filename or "file")
    stem, ext = os.path.splitext(name)
    ext = ext.lower()
    try:
        if ext == ".pdf":
            out, out_ext = compress_pdf(data, mode, ratio), ".pdf"
        elif ext in (".jpg", ".jpeg", ".png"):
            out, out_ext = compress_image(data, mode, ratio), ".jpg"
        else:
            raise PdfToolError(f"'{name}' is not a PDF, JPG or PNG.")
    except PdfToolError as e:
        return jsonify(error=str(e)), 400
    except Exception as e:
        return jsonify(error=f"Could not compress '{name}': {e}"), 400

    if len(out) >= len(data):
        out, out_ext = data, ext  # already as small as we can make it
    mime = ("application/pdf" if out_ext == ".pdf"
            else f"image/{out_ext.lstrip('.').replace('jpg', 'jpeg')}")
    return send_file(io.BytesIO(out), mimetype=mime, as_attachment=True,
                     download_name=output_name(f"{stem}_compressed{out_ext}",
                                               out_ext))


# ---------- unlock ----------

def unlock_pdf_bytes(data, password):
    """A copy of a PDF with its protection gone, and how it was opened.

    "Unlocked" here means the file is free of PDF security altogether: no
    password is needed to open it, and the permission flags that block
    printing, copying or editing are gone with the encryption that carried
    them — so the result can be shared and used like any ordinary PDF.
    """
    reader = PdfReader(io.BytesIO(data))
    if not reader.is_encrypted:
        raise PdfToolError("This PDF is not protected — there is nothing to unlock.")

    try:
        opened = reader.decrypt(password)
    except DependencyError:
        raise PdfToolError(
            "This PDF uses AES encryption, which needs the 'cryptography' "
            "package. Install it with: .venv/bin/pip install -r requirements.txt")
    except NotImplementedError as e:
        raise PdfToolError(f"This PDF uses an encryption this tool cannot open: {e}")
    except Exception as e:
        raise PdfToolError(f"Could not decrypt this PDF: {e}")

    if opened == PasswordType.NOT_DECRYPTED:
        raise PdfToolError(
            "That password did not open this PDF — check it and try again."
            if password else
            "This PDF needs a password to open — enter it above.")

    # Cloning pulls every object through the decryption filter, and the writer
    # emits them plain: no /Encrypt dictionary and no permission flags survive.
    try:
        writer = PdfWriter(clone_from=reader)
        out = io.BytesIO()
        writer.write(out)
    except FileNotDecryptedError:
        raise PdfToolError("That password opens the file but cannot decrypt its contents.")

    how = ("owner password (restrictions removed)"
           if opened == PasswordType.OWNER_PASSWORD else "user password")
    return out.getvalue(), how


@app.post("/api/unlock")
@logged("unlock")
def unlock_file():
    files = request.files.getlist("files")
    if not files:
        return jsonify(error="Upload a protected PDF to unlock."), 400
    if len(files) > 1:
        return jsonify(error="Unlock one file at a time."), 400

    f = files[0]
    name = os.path.basename(f.filename or "document.pdf")
    if not name.lower().endswith(".pdf"):
        return jsonify(error=f"'{name}' is not a PDF."), 400

    # The password is read straight into a local and never logged: the @logged
    # decorator only records the form fields it names, and this is not one.
    password = request.form.get("password", "")
    try:
        out, how = unlock_pdf_bytes(f.read(), password)
    except PdfToolError as e:
        return jsonify(error=str(e)), 400
    except Exception as e:
        return jsonify(error=f"Could not unlock '{name}': {e}"), 400

    log_event("info", "unlock", f"Opened '{name}' with its {how}")
    stem = os.path.splitext(name)[0]
    return send_file(io.BytesIO(out), mimetype="application/pdf", as_attachment=True,
                     download_name=output_name(f"{stem}_unlocked"))


def open_browser():
    """Hand the tab its key directly; it is swapped for a cookie on arrival."""
    webbrowser.open(f"http://{HOST}:{PORT}/?{TOKEN_PARAM}={SESSION_TOKEN}")


def main():
    threading.Thread(target=idle_watchdog, daemon=True).start()
    Timer(1.0, open_browser).start()
    log_event("info", "server", f"PDF Tool started on http://{HOST}:{PORT}")
    print(f"\n  PDF Tool running at http://{HOST}:{PORT}  (Ctrl+C to stop)")
    if sys.stdout.isatty():
        # Only ever to a terminal: the launcher redirects stdout into
        # server.log, which is world-readable.
        print(f"  If the browser did not open, use this link — it carries this\n"
              f"  run's key:  http://{HOST}:{PORT}/?{TOKEN_PARAM}={SESSION_TOKEN}")
    print()
    app.run(host=HOST, port=PORT, debug=False)


if __name__ == "__main__":
    main()
