"""Minimal local web page: upload a Quest PDF, download the Morpheus reports as a zip.

Run with:  python -m pgx_translator.web   then open http://127.0.0.1:5000
"""

from __future__ import annotations

import io
import tempfile
import zipfile
from pathlib import Path

from flask import Flask, render_template_string, request, send_file

from .convert import convert

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024

PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>Morpheus PGx Translator</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
 body{font-family:system-ui,sans-serif;background:#F3F7FA;color:#21364D;margin:0}
 header{background:#10243C;color:#fff;padding:18px 24px;font-weight:700;letter-spacing:.04em}
 main{max-width:560px;margin:32px auto;background:#fff;padding:24px;border-radius:8px}
 button{background:#155B93;color:#fff;border:0;padding:10px 18px;border-radius:6px;font-size:15px}
 .err{color:#AA263A;font-weight:600} small{color:#4D657C}
</style></head><body>
<header>MORPHEUS &nbsp;|&nbsp; PGx REPORT TRANSLATOR</header>
<main>
 <p>Upload a Quest Diagnostics Pharmacogenomics Panel PDF. You'll get a zip with the one-page
 summary (PDF) and the full report (Word + PDF).</p>
 {% if error %}<p class="err">{{ error }}</p>{% endif %}
 <form method="post" enctype="multipart/form-data">
  <p><input type="file" name="report" accept="application/pdf" required></p>
  <button type="submit">Convert</button>
 </form>
 <p><small>Files are processed locally and are not stored.</small></p>
</main></body></html>"""


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "GET":
        return render_template_string(PAGE, error=None)
    f = request.files.get("report")
    if not f or not f.filename:
        return render_template_string(PAGE, error="Choose a PDF first.")
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "quest.pdf"
        f.save(src)
        try:
            out = convert(src, Path(tmp) / "out")
        except Exception as e:
            return render_template_string(PAGE, error=f"Could not convert this file: {e}")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for p in out.files:
                z.write(p, p.name)
        buf.seek(0)
    name = f"Morpheus_PGx_{out.summary.report.patient.file_stub}.zip"
    return send_file(buf, mimetype="application/zip", as_attachment=True, download_name=name)


def main():
    app.run(host="127.0.0.1", port=5000, debug=False)


if __name__ == "__main__":
    main()
