"""Minimal local web page: upload a Quest PDF, add the patient's medications, download the reports as a zip.

Run with:  python -m pgx_translator.web   then open http://127.0.0.1:5000
"""

from __future__ import annotations

import io
import tempfile
import zipfile
from pathlib import Path

from flask import Flask, jsonify, render_template_string, request, send_file

from .convert import convert
from .medications import EXTRA_BY_NAME, NON_CPIC, match_entry, search_terms, split_entries

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024

PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>Morpheus PGx Translator</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
 body{font-family:system-ui,sans-serif;background:#F3F7FA;color:#21364D;margin:0}
 header{background:#10243C;color:#fff;padding:18px 24px;font-weight:700;letter-spacing:.04em}
 main{max-width:640px;margin:32px auto;background:#fff;padding:24px;border-radius:8px}
 h2{font-size:16px;margin:22px 0 6px}
 button{background:#155B93;color:#fff;border:0;padding:10px 18px;border-radius:6px;font-size:15px;cursor:pointer}
 button.small{padding:7px 12px;font-size:14px}
 input[type=text]{font-size:15px;padding:8px;width:70%;border:1px solid #B8C4CF;border-radius:6px}
 .err{color:#AA263A;font-weight:600} small{color:#4D657C}
 ul#meds{list-style:none;padding:0;margin:10px 0}
 ul#meds li{border:2px solid #B8C4CF;border-radius:6px;padding:6px 10px;margin:6px 0;display:flex;
            justify-content:space-between;align-items:center;gap:8px}
 ul#meds li.ok{border-color:#155B93} ul#meds li.warn{border-color:#E0A100;background:#FFF8E8}
 ul#meds li.none{border-color:#B8C4CF;background:#F6F7F8}
 .x{background:none;color:#AA263A;font-size:18px;padding:0 4px}
</style></head><body>
<header>MORPHEUS &nbsp;|&nbsp; PGx REPORT TRANSLATOR</header>
<main>
 <p>Upload a Quest Diagnostics Pharmacogenomics Panel PDF and, optionally, the patient's current medications.
 You'll get a zip with the one-page summary (PDF) and the full report (Word + PDF).</p>
 {% if error %}<p class="err">{{ error }}</p>{% endif %}
 <form method="post" enctype="multipart/form-data" id="f">
  <h2>1. Quest report</h2>
  <input type="file" name="report" accept="application/pdf" required>
  <h2>2. Patient medications <small>(optional)</small></h2>
  <input type="text" id="med" list="drugs" placeholder="Type a generic or brand name, e.g. Lipitor 40 mg"
         autocomplete="off">
  <button type="button" class="small" id="add">Add</button>
  <datalist id="drugs">{% for t in terms %}<option value="{{ t }}">{% endfor %}</datalist>
  <ul id="meds"></ul>
  <small>Or paste a list (one per line):</small><br>
  <textarea id="paste" rows="3" style="width:95%;margin-top:4px"></textarea>
  <button type="button" class="small" id="addall">Add list</button>
  <input type="hidden" name="meds" id="medsfield">
  <p style="margin-top:22px"><button type="submit">Convert</button></p>
 </form>
 <p><small>Files are processed on this computer and are not stored.</small></p>
</main>
<script>
const meds = [];
const ul = document.getElementById('meds');
function render(){
  ul.innerHTML = '';
  meds.forEach((m, i) => {
    const li = document.createElement('li');
    li.className = m.cls;
    li.innerHTML = '<span><b></b> <small></small></span>';
    li.querySelector('b').textContent = m.entered;
    li.querySelector('small').textContent = m.note;
    const x = document.createElement('button'); x.type='button'; x.className='x'; x.textContent='×';
    x.onclick = () => { meds.splice(i, 1); render(); };
    li.appendChild(x); ul.appendChild(li);
  });
  document.getElementById('medsfield').value = meds.map(m => m.entered).join('\\n');
}
async function add(text){
  text = text.trim(); if(!text) return;
  const r = await fetch('/check?q=' + encodeURIComponent(text)); const j = await r.json();
  meds.push({entered: text, cls: j.cls, note: j.note}); render();
}
document.getElementById('add').onclick = () => { const i = document.getElementById('med'); add(i.value); i.value=''; i.focus(); };
document.getElementById('med').addEventListener('keydown', e => {
  if(e.key === 'Enter'){ e.preventDefault(); document.getElementById('add').click(); } });
document.getElementById('addall').onclick = async () => {
  const t = document.getElementById('paste'); for(const line of t.value.split(/[\\n;,]+/)) await add(line); t.value=''; };
document.getElementById('f').addEventListener('submit', () => {
  const pending = document.getElementById('med').value.trim();
  if (pending) { meds.push({entered: pending}); document.getElementById('medsfield').value = meds.map(m => m.entered).join('\\n'); }
});
</script>
</body></html>"""


@app.route("/check")
def check():
    """Live feedback for one typed medication."""
    m = match_entry(request.args.get("q", ""))
    if not m.names:
        return jsonify(cls="warn", note="— not recognized; check the spelling or use the generic name")
    names = ", ".join(m.names)
    if m.fuzzy:
        return jsonify(cls="warn", note=f"→ matched {names} by approximate spelling; please confirm")
    if all(n in NON_CPIC for n in m.names):
        return jsonify(cls="none", note=f"→ {names}: no CPIC gene–drug guideline")
    if all(n in EXTRA_BY_NAME and EXTRA_BY_NAME[n].short.startswith("No CPIC") for n in m.names):
        return jsonify(cls="none", note=f"→ {names}: CPIC reviewed, no gene-based recommendation")
    return jsonify(cls="ok", note=f"→ {names}")


@app.route("/", methods=["GET", "POST"])
def index():
    terms = search_terms()
    if request.method == "GET":
        return render_template_string(PAGE, error=None, terms=terms)
    f = request.files.get("report")
    if not f or not f.filename:
        return render_template_string(PAGE, error="Choose a PDF first.", terms=terms)
    meds = split_entries(request.form.get("meds", ""))
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "quest.pdf"
        f.save(src)
        try:
            out = convert(src, Path(tmp) / "out", medications=meds)
        except Exception as e:
            return render_template_string(PAGE, error=f"Could not convert this file: {e}", terms=terms)
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
