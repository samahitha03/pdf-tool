"""Local PDF Tool — merge, split, organize PDFs and convert images to PDF.

Runs entirely on your machine. Start with ./run.sh and the UI opens
in your browser at http://127.0.0.1:5177
"""

import io
import json
import os
import time
import threading
import webbrowser
import zipfile
from threading import Timer

from flask import Flask, request, send_file, send_from_directory, jsonify
from pypdf import PdfWriter, PdfReader
from PIL import Image

HOST = "127.0.0.1"
PORT = 5177
# Shut down after this many seconds with no open tabs (heartbeats)
IDLE_TIMEOUT = int(os.environ.get("PDF_TOOL_IDLE_TIMEOUT", "600"))
MAX_CONTENT_LENGTH = int(os.environ.get("PDF_TOOL_MAX_CONTENT_LENGTH", str(50 * 1024 * 1024)))

app = Flask(__name__, static_folder="static")
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

last_activity = time.time()


@app.before_request
def touch_activity():
    global last_activity
    last_activity = time.time()


@app.post("/api/heartbeat")
def heartbeat():
    return jsonify(ok=True)


def idle_watchdog():
    while True:
        time.sleep(min(30, IDLE_TIMEOUT / 2))
        if time.time() - last_activity > IDLE_TIMEOUT:
            print(f"No activity for {IDLE_TIMEOUT}s — shutting down.")
            os._exit(0)

# A4 and Letter sizes in PDF points (72 pt per inch)
PAGE_SIZES = {
    "a4": (595.0, 842.0),
    "letter": (612.0, 792.0),
}


@app.get("/")
def index():
    return send_from_directory("static", "index.html")


class PdfToolError(ValueError):
    """A user-facing error (bad input, unreadable file)."""


def read_pdf(f):
    reader = PdfReader(io.BytesIO(f.read()))
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception:
            raise PdfToolError(f"'{f.filename}' is password-protected.")
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


def open_browser():
    webbrowser.open(f"http://{HOST}:{PORT}")


def main():
    threading.Thread(target=idle_watchdog, daemon=True).start()
    Timer(1.0, open_browser).start()
    print(f"\n  PDF Tool running at http://{HOST}:{PORT}  (Ctrl+C to stop)\n")
    app.run(host=HOST, port=PORT, debug=False)


if __name__ == "__main__":
    main()
