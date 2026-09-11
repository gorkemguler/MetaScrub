from __future__ import annotations

import io
import os
import threading
import webbrowser
import zipfile
from datetime import datetime

from flask import Flask, Response, abort, request, send_file
from werkzeug.utils import secure_filename

from ._theme import full_css
from .cleaner import clean_file_list
from .config import CONTAINER_EXTENSIONS, MEDIA_EXTENSIONS, CleanConfig
from .engines import format_support, supported_extensions
from .report import render_html_report, render_json_report

# 200 MB per upload batch — a local single-user tool, but still worth
# bounding so a stray multi-GB drop doesn't fill memory/disk.
_MAX_CONTENT_LENGTH = 200 * 1024 * 1024

_STR = {
    "en": {
        "tagline": "drop files in, get them back scrubbed",
        "drop": "Drop PDF / Office / image / SVG files here, or click to choose",
        "opts": "Options",
        "keep_title": "Keep the document title",
        "keep_icc": "Keep image colour profile",
        "opt_media": "Also scrub audio / video files",
        "opt_recurse": "Look inside archives (.zip, .tar, .7z, .eml)",
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
        "local_only": "local, single-user — no authentication, don't expose it to a network",
        "sum_removed": "fields removed",
        "sum_files": "files",
        "sum_residual": "with residual",
    },
    "tr": {
        "tagline": "dosyaları bırak, temizlenmiş halde geri al",
        "drop": "PDF / Office / görsel / SVG dosyalarını buraya bırak ya da seçmek için tıkla",
        "opts": "Seçenekler",
        "keep_title": "Belge başlığını koru",
        "keep_icc": "Görsel renk profilini koru",
        "opt_media": "Ses / video dosyalarını da temizle",
        "opt_recurse": "Arşivlerin içine bak (.zip, .tar, .7z, .eml)",
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
        "local_only": "yerel, tek kullanıcılık — kimlik doğrulama yok, ağa açmayın",
        "sum_removed": "alan silindi",
        "sum_files": "dosya",
        "sum_residual": "artık kalan",
    },
}

_EXTRA_CSS = """
.msc-drop { border:2px dashed var(--border); border-radius:14px; padding:46px 20px; text-align:center;
  color:var(--muted); cursor:pointer; transition:.15s; background:var(--panel-2); }
.msc-drop.hot { border-color:var(--accent); color:var(--text);
  background:color-mix(in srgb,var(--accent) 8%,var(--panel-2)); }
.msc-files { list-style:none; padding:0; margin:14px 0 0; font-size:13px; color:var(--muted); }
label.msc-opt { display:flex; align-items:center; gap:8px; margin:10px 0; font-size:13px; }
.msc-form h4 { margin:20px 0 6px; font-size:12px; letter-spacing:.05em; text-transform:uppercase;
  color:var(--muted); }
.msc-spin { display:inline-block; width:14px; height:14px; border:2px solid color-mix(in srgb,var(--accent) 30%,transparent);
  border-top-color:var(--accent); border-radius:50%; animation:msc-spin .8s linear infinite;
  vertical-align:middle; margin-right:8px; }
@keyframes msc-spin { to { transform:rotate(360deg); } }
select { background:var(--panel); color:var(--text); border:1px solid var(--border);
  border-radius:7px; padding:5px 8px; font-size:13px; }
"""


def _page(lang: str, active: str, body: str) -> str:
    s = _STR.get(lang, _STR["en"])
    return f"""<!DOCTYPE html><html lang="{lang}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>MetaCLS</title>
<style>{full_css()}{_EXTRA_CSS}</style></head><body>
<div class="msc-header">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:12px">
    <div>
      <div class="msc-mark">meta<b>cls</b></div>
      <div class="msc-tag">{s['tagline']} &nbsp;·&nbsp; {s['local_only']}</div>
      <div class="msc-nav">
        <a href="/?lang={lang}" class="{'on' if active=='new' else ''}">{s['nav_new']}</a>
        <a href="/history?lang={lang}" class="{'on' if active=='history' else ''}">{s['nav_history']}</a>
      </div>
    </div>
    <div class="msc-lang">
      <a href="?lang=en" class="{'on' if lang=='en' else ''}">EN</a>
      <a href="?lang=tr" class="{'on' if lang=='tr' else ''}">TR</a>
    </div>
  </div>
</div><div class="msc-main">{body}</div></body></html>"""


def _form(lang: str, error: str | None = None) -> str:
    s = _STR.get(lang, _STR["en"])
    exts = " ".join(sorted("." + e for e in supported_extensions()))
    err = (f'<div class="msc-card is-error" style="color:var(--bad)">{_esc(error)}</div>'
           if error else "")
    body = f"""{err}
<form class="msc-card msc-form" method="post" action="/clean" enctype="multipart/form-data" id="f">
  <input type="hidden" name="lang" value="{lang}">
  <div class="msc-drop" id="drop">{s['drop']}
    <div class="msc-meta" style="margin-top:8px">{exts}</div>
    <ul class="msc-files" id="files"></ul></div>
  <input type="file" name="files" id="input" multiple style="display:none">
  <h4>{s['opts']}</h4>
  <label class="msc-opt"><input type="checkbox" name="keep_title"> {s['keep_title']}</label>
  <label class="msc-opt"><input type="checkbox" name="keep_icc" checked> {s['keep_icc']}</label>
  <label class="msc-opt"><input type="checkbox" name="media"> {s['opt_media']}</label>
  <label class="msc-opt"><input type="checkbox" name="recurse"> {s['opt_recurse']}</label>
  <label class="msc-opt">{s['lang']}:
    <select name="report_lang">
      <option value="en"{' selected' if lang=='en' else ''}>English</option>
      <option value="tr"{' selected' if lang=='tr' else ''}>Türkçe</option>
    </select></label>
  <button type="submit" class="msc-btn" id="btn" data-working="{s['working']}"
    style="margin-top:14px">{s['submit']}</button>
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
  btn.innerHTML='<span class="msc-spin"></span>'+btn.dataset.working;}}}});
</script>"""
    return _page(lang, "new", body)


def _results(lang: str, run_id: str, report) -> str:
    s = _STR.get(lang, _STR["en"])
    state = "bad" if report.errored else ("warn" if report.files_with_residual else "ok")
    state_word = {"ok": "SCRUBBED", "warn": "RESIDUAL METADATA", "bad": "ERRORS"}[state]

    cards = []
    for r in sorted(report.results, key=lambda x: (x.status != "error", x.src_path)):
        name = os.path.basename(r.src_path)
        rows = "".join(
            f"<tr><td>{_esc(c.namespace)}</td><td>{_esc(c.field)}</td>"
            f"<td class='was'>{_esc(c.before)}</td></tr>"
            for c in r.removed
        )
        table = (f"<table class='msc-diff'><thead><tr><th>Group</th><th>Field</th>"
                 f"<th>Old value</th></tr></thead><tbody>{rows}</tbody></table>") if rows \
            else f"<div class='msc-empty'>{s['res_none']}</div>"
        residual = (f"<div class='msc-residual'>⚠ {s['res_residual']}: {_esc(', '.join(r.residual))}</div>"
                    if r.residual else "")
        detail = (f" <span class='msc-meta'>{_esc(r.reason or r.error or '')}</span>"
                  if (r.reason or r.error) else "")
        dl = (f"<div class='msc-actions' style='margin-top:10px'>"
              f"<a href='/file/{run_id}/{_esc(os.path.basename(r.out_path))}'>{s['res_dl_one']}</a></div>"
              if r.status == "cleaned" and r.out_path else "")
        cards.append(
            f"<div class='msc-card is-{r.status}'><div class='msc-file'>{_esc(name)}</div>"
            f"<div style='margin:7px 0'><span class='msc-pill {r.status}'>{r.status}</span>{detail} "
            f"<span class='msc-meta'>&nbsp;{len(r.removed)} {s['res_removed']}</span></div>"
            f"{table}{residual}{dl}</div>"
        )

    hero = (
        f"<div class='msc-hero'><div class='msc-hero-band'>"
        f"<span class='msc-hero-state {state}'>{state_word}</span>"
        f"<span class='msc-hero-sub'>{run_id}</span></div>"
        f"<div class='msc-stats'>"
        f"<div class='msc-stat'><div class='n'>{len(report.results)}</div><div class='l'>{s['sum_files']}</div></div>"
        f"<div class='msc-stat'><div class='n'>{report.fields_removed}</div><div class='l'>{s['sum_removed']}</div></div>"
        f"<div class='msc-stat {'warn' if report.files_with_residual else ''}'>"
        f"<div class='n'>{len(report.files_with_residual)}</div><div class='l'>{s['sum_residual']}</div></div>"
        f"</div><div class='msc-src' style='padding:0 22px 18px'>"
        f"<span class='msc-actions'>"
        f"<a href='/zip/{run_id}'>{s['res_dl_all']}</a>"
        f"<a href='/report/{run_id}?lang={lang}'>{s['res_report']}</a>"
        f"<a href='/?lang={lang}'>{s['back']}</a></span></div></div>"
    )
    return _page(lang, "new", hero + "".join(cards))


class _WebApp:
    def __init__(self, output_dir: str) -> None:
        # realpath, not abspath: the traversal guard in run_dir() compares
        # against a realpath'd candidate, so the base must be resolved too
        # or a legitimate run under a symlinked dir (e.g. /tmp -> /private/tmp
        # on macOS) is wrongly rejected.
        self.output_dir = os.path.realpath(output_dir)
        os.makedirs(self.output_dir, exist_ok=True)

    def run_dir(self, run_id: str) -> str | None:
        if not run_id or "/" in run_id or "\\" in run_id or run_id in (".", ".."):
            return None
        p = os.path.realpath(os.path.join(self.output_dir, run_id))
        if p != self.output_dir and not p.startswith(self.output_dir + os.sep):
            return None
        return p if os.path.isdir(p) else None


def create_app(output_dir: str = "./metacls_cleaned") -> Flask:
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

    @app.get("/formats")
    def formats() -> Response:
        import json as _json

        return Response(_json.dumps(format_support(), ensure_ascii=False),
                        mimetype="application/json")

    @app.post("/clean")
    def clean():
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
            name = secure_filename(f.filename or "") or "file"
            dest = os.path.join(up_dir, name)
            stem, ext = os.path.splitext(dest)
            n = 1
            while dest in saved or os.path.exists(dest):
                dest = f"{stem}({n}){ext}"
                n += 1
            f.save(dest)
            saved.append(dest)

        recurse = bool(request.form.get("recurse"))
        filetypes = list(CleanConfig().filetypes)
        if request.form.get("media"):
            filetypes = sorted(set(filetypes) | MEDIA_EXTENSIONS)
        if recurse:
            filetypes = sorted(set(filetypes) | CONTAINER_EXTENSIONS)
        cfg = CleanConfig(
            filetypes=filetypes,
            output_dir=out_dir,
            keep_fields=["Title"] if request.form.get("keep_title") else [],
            keep_color_profile=bool(request.form.get("keep_icc")),
            recurse=recurse,
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
                         download_name=f"metacls-{run_id}.zip")

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
        runs = [
            name for name in sorted(os.listdir(state.output_dir), reverse=True)
            if os.path.isfile(os.path.join(state.output_dir, name, "report.json"))
        ]
        if not runs:
            body = f"<div class='msc-card'>{s['hist_empty']}</div>"
        else:
            items = "".join(
                f"<div class='msc-card'><span class='msc-file'>{_esc(r)}</span>"
                f"<div class='msc-actions' style='margin-top:8px'>"
                f"<a href='/report/{_esc(r)}?lang={lang}'>{s['hist_open']}</a>"
                f"<a href='/zip/{_esc(r)}'>{s['hist_zip']}</a></div></div>"
                for r in runs
            )
            body = f"<h3 class='msc-h' style='color:var(--muted);text-transform:uppercase;" \
                   f"font-size:13px;letter-spacing:.04em'>{s['hist_title']}</h3>{items}"
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
