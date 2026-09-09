from __future__ import annotations

import io
import os
import shutil
import threading
import webbrowser
import zipfile
from datetime import datetime

from flask import Flask, Response, abort, redirect, request, send_file
from werkzeug.utils import secure_filename

from .cleaner import clean_file_list
from .config import CleanConfig
from .engines import supported_extensions
from .report import render_html_report, render_json_report

# 200 MB per upload batch — a local single-user tool, but still worth
# bounding so a stray multi-GB drop doesn't fill memory/disk.
_MAX_CONTENT_LENGTH = 200 * 1024 * 1024

_STR = {
    "en": {
        "tagline": "Drag files in, get them back with the metadata stripped",
        "drop": "Drop PDF / Office / image files here, or click to choose",
        "opts": "Options",
        "keep_title": "Keep the document title",
        "keep_icc": "Keep image colour profile",
        "lang": "Report language",
        "submit": "Scrub metadata",
        "working": "Scrubbing…",
        "nav_new": "New batch",
        "nav_history": "History",
        "res_title": "Results",
        "res_removed": "removed",
        "res_residual": "residual",
        "res_dl_all": "Download all (.zip)",
        "res_dl_one": "Download",
        "res_report": "Full report",
        "res_none": "No metadata was found in this file.",
        "back": "← Scrub more files",
        "hist_title": "Past runs",
        "hist_empty": "Nothing yet — scrub a batch and it shows up here.",
        "hist_open": "Open report",
        "hist_zip": "Download (.zip)",
        "err_nofiles": "No files were uploaded.",
        "err_toobig": "Upload is larger than the 200 MB limit.",
        "local_only": "Local tool — don't expose this to the internet.",
    },
    "tr": {
        "tagline": "Dosyaları sürükle, metadata'sı silinmiş halde geri al",
        "drop": "PDF / Office / görsel dosyalarını buraya bırak ya da seçmek için tıkla",
        "opts": "Seçenekler",
        "keep_title": "Belge başlığını koru",
        "keep_icc": "Görsel renk profilini koru",
        "lang": "Rapor dili",
        "submit": "Metadata'yı temizle",
        "working": "Temizleniyor…",
        "nav_new": "Yeni grup",
        "nav_history": "Geçmiş",
        "res_title": "Sonuçlar",
        "res_removed": "silindi",
        "res_residual": "artık",
        "res_dl_all": "Hepsini indir (.zip)",
        "res_dl_one": "İndir",
        "res_report": "Tam rapor",
        "res_none": "Bu dosyada metadata bulunamadı.",
        "back": "← Daha fazla dosya temizle",
        "hist_title": "Önceki çalıştırmalar",
        "hist_empty": "Henüz yok — bir grup temizle, burada görünsün.",
        "hist_open": "Raporu aç",
        "hist_zip": "İndir (.zip)",
        "err_nofiles": "Hiç dosya yüklenmedi.",
        "err_toobig": "Yükleme 200 MB sınırını aşıyor.",
        "local_only": "Yerel araç — internete açmayın.",
    },
}

_CSS = """
:root { --bg:#0f1117; --panel:#161925; --border:#2a2f42; --text:#e6e8f0;
  --muted:#9aa1b4; --accent:#6ea8fe; --good:#7dd88f; --warn:#f2a65a; --bad:#f26d6d; }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--text);
  font-family:-apple-system,"Segoe UI",Roboto,sans-serif; font-size:14px; }
header { padding:24px 40px; border-bottom:1px solid var(--border); display:flex;
  justify-content:space-between; align-items:flex-start; flex-wrap:wrap; gap:12px; }
.banner { color:#8bb4ff; font-weight:800; font-size:22px; }
.meta { color:var(--muted); font-size:13px; margin-top:4px; }
.nav a { color:var(--muted); text-decoration:none; font-size:12.5px; font-weight:600;
  margin-left:16px; } .nav a:hover { color:var(--text); }
.lang a { color:var(--muted); text-decoration:none; border:1px solid var(--border);
  border-radius:999px; padding:3px 10px; font-size:12px; font-weight:700; margin-left:6px; }
.lang a.on { background:var(--accent); color:var(--bg); border-color:var(--accent); }
main { padding:28px 40px 64px; max-width:820px; margin:0 auto; }
.card { background:var(--panel); border:1px solid var(--border); border-radius:12px;
  padding:22px; margin-bottom:18px; }
.drop { border:2px dashed var(--border); border-radius:12px; padding:44px 20px; text-align:center;
  color:var(--muted); cursor:pointer; transition:.15s; }
.drop.hot { border-color:var(--accent); color:var(--text); background:rgba(110,168,254,.06); }
.files { list-style:none; padding:0; margin:14px 0 0; font-size:13px; color:var(--muted); }
label.opt { display:flex; align-items:center; gap:8px; margin:10px 0; font-size:13px; }
button { background:var(--accent); color:#0f1117; border:0; border-radius:8px;
  padding:12px 22px; font-weight:800; font-size:14px; cursor:pointer; margin-top:14px; }
button:disabled { opacity:.6; cursor:wait; }
.pill { display:inline-block; font-size:11px; font-weight:700; padding:2px 9px; border-radius:999px;
  text-transform:uppercase; letter-spacing:.04em; }
.pill.cleaned{background:rgba(125,216,143,.15);color:var(--good);}
.pill.skipped{background:rgba(242,166,90,.15);color:var(--warn);}
.pill.unsupported{background:rgba(154,161,180,.15);color:var(--muted);}
.pill.error{background:rgba(242,109,109,.15);color:var(--bad);}
.fname { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; word-break:break-all; }
table { width:100%; border-collapse:collapse; margin-top:10px; font-size:12.5px; }
th,td { text-align:left; padding:5px 9px; border-bottom:1px solid var(--border); vertical-align:top; }
th { color:var(--muted); font-weight:600; }
td.v { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; color:var(--muted); word-break:break-word; }
.residual { color:var(--bad); font-size:12px; margin-top:8px; }
a { color:var(--accent); }
.row-actions a { margin-right:14px; }
.spinner { display:inline-block; width:15px; height:15px; border:2px solid rgba(110,168,254,.25);
  border-top-color:var(--accent); border-radius:50%; animation:spin .8s linear infinite;
  vertical-align:middle; margin-right:8px; }
@keyframes spin { to { transform:rotate(360deg); } }
"""


def _page(lang: str, active: str, body: str) -> str:
    s = _STR.get(lang, _STR["en"])
    other = "tr" if lang == "en" else "en"
    return f"""<!DOCTYPE html><html lang="{lang}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>MetaScrub</title>
<style>{_CSS}</style></head><body>
<header>
  <div><div class="banner">MetaScrub</div><div class="meta">{s['tagline']}</div>
  <div class="meta">{s['local_only']}</div>
  <div class="nav" style="margin-top:8px">
    <a href="/?lang={lang}">{'• ' if active=='new' else ''}{s['nav_new']}</a>
    <a href="/history?lang={lang}">{'• ' if active=='history' else ''}{s['nav_history']}</a>
  </div></div>
  <div class="lang">
    <a href="?lang=en" class="{'on' if lang=='en' else ''}">EN</a>
    <a href="?lang=tr" class="{'on' if lang=='tr' else ''}">TR</a>
  </div>
</header><main>{body}</main></body></html>"""


def _form(lang: str, error: str | None = None) -> str:
    s = _STR.get(lang, _STR["en"])
    exts = " ".join(sorted("." + e for e in supported_extensions()))
    err = f'<div class="card" style="border-color:var(--bad);color:var(--bad)">{error}</div>' if error else ""
    body = f"""{err}
<form class="card" method="post" action="/clean" enctype="multipart/form-data" id="f">
  <input type="hidden" name="lang" value="{lang}">
  <div class="drop" id="drop">{s['drop']}<div class="meta" style="margin-top:8px">{exts}</div>
    <ul class="files" id="files"></ul></div>
  <input type="file" name="files" id="input" multiple style="display:none">
  <h4>{s['opts']}</h4>
  <label class="opt"><input type="checkbox" name="keep_title"> {s['keep_title']}</label>
  <label class="opt"><input type="checkbox" name="keep_icc" checked> {s['keep_icc']}</label>
  <label class="opt">{s['lang']}:
    <select name="report_lang">
      <option value="en"{' selected' if lang=='en' else ''}>English</option>
      <option value="tr"{' selected' if lang=='tr' else ''}>Türkçe</option>
    </select></label>
  <button type="submit" id="btn" data-working="{s['working']}">{s['submit']}</button>
</form>
<script>
var drop=document.getElementById('drop'),inp=document.getElementById('input'),
    fl=document.getElementById('files'),f=document.getElementById('f'),btn=document.getElementById('btn');
function show(){{fl.innerHTML='';for(var i=0;i<inp.files.length;i++){{var li=document.createElement('li');
  li.textContent='• '+inp.files[i].name;fl.appendChild(li);}}}}
drop.onclick=function(){{inp.click();}};inp.onchange=show;
['dragenter','dragover'].forEach(function(e){{drop.addEventListener(e,function(ev){{ev.preventDefault();
  drop.classList.add('hot');}});}});
['dragleave','drop'].forEach(function(e){{drop.addEventListener(e,function(ev){{ev.preventDefault();
  drop.classList.remove('hot');}});}});
drop.addEventListener('drop',function(ev){{inp.files=ev.dataTransfer.files;show();}});
f.addEventListener('submit',function(){{if(inp.files.length){{btn.disabled=true;
  btn.innerHTML='<span class="spinner"></span>'+btn.dataset.working;}}}});
</script>"""
    return _page(lang, "new", body)


def _results(lang: str, run_id: str, report) -> str:
    s = _STR.get(lang, _STR["en"])
    cards = []
    for r in sorted(report.results, key=lambda x: (x.status != "error", x.src_path)):
        name = os.path.basename(r.src_path)
        rows = "".join(
            f"<tr><td>{_esc(c.namespace)}</td><td>{_esc(c.field)}</td><td class='v'>{_esc(c.before)}</td></tr>"
            for c in r.removed
        )
        table = (f"<table><thead><tr><th>Group</th><th>Field</th><th>Old value</th></tr></thead>"
                 f"<tbody>{rows}</tbody></table>") if rows else f"<div class='meta'>{s['res_none']}</div>"
        residual = (f"<div class='residual'>⚠ {s['res_residual']}: {_esc(', '.join(r.residual))}</div>"
                    if r.residual else "")
        detail = f" <span class='meta'>{_esc(r.reason or r.error or '')}</span>" if (r.reason or r.error) else ""
        dl = (f"<div class='row-actions' style='margin-top:10px'>"
              f"<a href='/file/{run_id}/{_esc(os.path.basename(r.out_path))}'>{s['res_dl_one']}</a></div>"
              if r.status == "cleaned" and r.out_path else "")
        cards.append(
            f"<div class='card'><div class='fname'>{_esc(name)}</div>"
            f"<div style='margin:6px 0'><span class='pill {r.status}'>{r.status}</span>{detail} "
            f"<span class='meta'>{len(r.removed)} {s['res_removed']}</span></div>"
            f"{table}{residual}{dl}</div>"
        )
    head = (f"<div class='card'><b>{s['res_title']}</b> — "
            f"{report.fields_removed} field(s) removed across {len(report.results)} file(s)"
            f"<div class='row-actions' style='margin-top:12px'>"
            f"<a href='/zip/{run_id}'>{s['res_dl_all']}</a>"
            f"<a href='/report/{run_id}?lang={lang}'>{s['res_report']}</a>"
            f"<a href='/?lang={lang}'>{s['back']}</a></div></div>")
    return _page(lang, "new", head + "".join(cards))


class _WebApp:
    def __init__(self, output_dir: str) -> None:
        self.output_dir = os.path.abspath(output_dir)
        os.makedirs(self.output_dir, exist_ok=True)

    def run_dir(self, run_id: str) -> str | None:
        if not run_id or "/" in run_id or "\\" in run_id or run_id in (".", ".."):
            return None
        p = os.path.realpath(os.path.join(self.output_dir, run_id))
        if p != self.output_dir and not p.startswith(self.output_dir + os.sep):
            return None
        return p if os.path.isdir(p) else None


def create_app(output_dir: str = "./metascrub_cleaned") -> Flask:
    state = _WebApp(output_dir)
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = _MAX_CONTENT_LENGTH

    @app.errorhandler(413)
    def _too_big(_e):  # noqa: ANN001
        lang = _lang(request.args.get("lang"))
        return _form(lang, _STR[lang]["err_toobig"]), 413

    @app.get("/")
    def index() -> str:
        return _form(_lang(request.args.get("lang")))

    @app.post("/clean")
    def clean() -> Response | str:
        lang = _lang(request.form.get("lang"))
        uploads = [f for f in request.files.getlist("files") if f and f.filename]
        if not uploads:
            return _form(lang, _STR[lang]["err_nofiles"]), 400

        run_id = "web-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3]
        run_path = os.path.join(state.output_dir, run_id)
        up_dir = os.path.join(run_path, "uploads")
        out_dir = os.path.join(run_path, "cleaned")
        os.makedirs(up_dir, exist_ok=True)

        saved: list[str] = []
        for f in uploads:
            name = secure_filename(f.filename) or "file"
            dest = os.path.join(up_dir, name)
            stem, ext = os.path.splitext(dest)
            n = 1
            while dest in saved or os.path.exists(dest):
                dest = f"{stem}({n}){ext}"
                n += 1
            f.save(dest)
            saved.append(dest)

        cfg = CleanConfig(
            output_dir=out_dir,
            keep_fields=["Title"] if request.form.get("keep_title") else [],
            keep_color_profile=bool(request.form.get("keep_icc")),
        )
        report = clean_file_list(saved, cfg, base_dir=up_dir)

        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(run_path, "report.json"), "w", encoding="utf-8") as fh:
            fh.write(render_json_report(report))
        with open(os.path.join(run_path, "report.html"), "w", encoding="utf-8") as fh:
            fh.write(render_html_report(report, lang=_lang(request.form.get("report_lang"))))

        return _results(lang, run_id, report)

    @app.get("/file/<run_id>/<path:name>")
    def one_file(run_id: str, name: str) -> Response:
        rd = state.run_dir(run_id)
        if not rd:
            abort(404)
        safe = secure_filename(name)
        path = os.path.realpath(os.path.join(rd, "cleaned", safe))
        if not path.startswith(os.path.join(rd, "cleaned")) or not os.path.isfile(path):
            abort(404)
        return send_file(path, as_attachment=True, download_name=safe)

    @app.get("/zip/<run_id>")
    def zip_run(run_id: str) -> Response:
        rd = state.run_dir(run_id)
        if not rd:
            abort(404)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            cleaned = os.path.join(rd, "cleaned")
            for root, _, files in os.walk(cleaned):
                for fn in files:
                    full = os.path.join(root, fn)
                    zf.write(full, os.path.join("cleaned", os.path.relpath(full, cleaned)))
            for meta in ("report.json", "report.html"):
                p = os.path.join(rd, meta)
                if os.path.isfile(p):
                    zf.write(p, meta)
        buf.seek(0)
        return send_file(buf, mimetype="application/zip", as_attachment=True,
                         download_name=f"metascrub-{run_id}.zip")

    @app.get("/report/<run_id>")
    def report(run_id: str) -> Response:
        rd = state.run_dir(run_id)
        if not rd or not os.path.isfile(os.path.join(rd, "report.html")):
            abort(404)
        with open(os.path.join(rd, "report.html"), encoding="utf-8") as fh:
            return Response(fh.read(), mimetype="text/html")

    @app.get("/history")
    def history() -> str:
        lang = _lang(request.args.get("lang"))
        s = _STR[lang]
        runs = []
        for name in sorted(os.listdir(state.output_dir), reverse=True):
            if os.path.isfile(os.path.join(state.output_dir, name, "report.json")):
                runs.append(name)
        if not runs:
            body = f"<div class='card'>{s['hist_empty']}</div>"
        else:
            items = "".join(
                f"<div class='card'><span class='fname'>{_esc(r)}</span>"
                f"<div class='row-actions' style='margin-top:8px'>"
                f"<a href='/report/{_esc(r)}?lang={lang}'>{s['hist_open']}</a>"
                f"<a href='/zip/{_esc(r)}'>{s['hist_zip']}</a></div></div>"
                for r in runs
            )
            body = f"<h3>{s['hist_title']}</h3>{items}"
        return _page(lang, "history", body)

    return app


def run_server(*, host: str, port: int, output_dir: str, open_browser: bool) -> None:
    app = create_app(output_dir)
    if open_browser:
        threading.Timer(0.7, lambda: webbrowser.open(f"http://{host}:{port}/")).start()
    app.run(host=host, port=port)


def _lang(v: str | None) -> str:
    return v if v in _STR else "en"


def _esc(text: str) -> str:
    return (
        str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )
