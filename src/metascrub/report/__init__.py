from __future__ import annotations

import json
import os
from datetime import datetime

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .._theme import full_css
from ..models import BatchReport, CleanResult

__all__ = ["render_json_report", "render_html_report"]

_TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")

_STATUS_ORDER = {"error": 0, "cleaned": 1, "skipped": 2, "unsupported": 3}


def render_json_report(report: BatchReport) -> str:
    payload = {
        "tool": "metascrub",
        "root": report.root,
        "started_at": report.started_at.isoformat(),
        "in_place": report.in_place,
        "dry_run": report.dry_run,
        "tool_versions": report.tool_versions,
        "summary": {
            "files": len(report.results),
            "by_status": report.counts,
            "fields_removed": report.fields_removed,
            "files_with_residual": len(report.files_with_residual),
            "files_errored": len(report.errored),
        },
        "files": [_file_dict(r) for r in _sorted(report.results)],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def render_html_report(report: BatchReport, *, lang: str = "en") -> str:
    env = Environment(
        loader=FileSystemLoader(_TEMPLATE_DIR),
        autoescape=select_autoescape(["html", "jinja"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template("report.html.jinja")
    if report.errored:
        state = "bad"
    elif report.files_with_residual and not report.dry_run:
        state = "warn"
    else:
        state = "ok"
    return template.render(
        report=report,
        results=_sorted(report.results),
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        S=_STRINGS.get(lang, _STRINGS["en"]),
        lang=lang if lang in _STRINGS else "en",
        css=full_css(),
        state=state,
    )


def _sorted(results: list[CleanResult]) -> list[CleanResult]:
    return sorted(results, key=lambda r: (_STATUS_ORDER.get(r.status, 9), r.src_path))


def _file_dict(r: CleanResult) -> dict:
    return {
        "src_path": r.src_path,
        "out_path": r.out_path,
        "filetype": r.filetype,
        "engine": r.engine,
        "status": r.status,
        "reason": r.reason,
        "error": r.error,
        "bytes_before": r.bytes_before,
        "bytes_after": r.bytes_after,
        "kept": r.kept,
        "residual": r.residual,
        "removed": [
            {"namespace": c.namespace, "field": c.field, "before": c.before, "after": c.after}
            for c in r.removed
        ],
    }


_STRINGS = {
    "en": {
        "title": "MetaScrub report",
        "tagline": "Metadata scrub — before / after",
        "generated": "Generated",
        "root": "Source",
        "mode": "Mode",
        "mode_inplace": "in-place (originals overwritten)",
        "mode_copy": "cleaned copies",
        "mode_dryrun": "dry-run (nothing written)",
        "sum_files": "Files",
        "sum_removed": "Metadata fields removed",
        "sum_residual": "Files with residual metadata",
        "sum_errors": "Errors",
        "col_field": "Field",
        "col_namespace": "Group",
        "col_before": "Old value",
        "kept": "Kept (by request)",
        "residual": "Still present after cleaning — verify manually",
        "no_meta": "No metadata found.",
        "out": "Output",
        "size": "Size",
        "status_cleaned": "cleaned",
        "status_skipped": "skipped",
        "status_unsupported": "unsupported",
        "status_error": "error",
        "would_remove": "Would remove",
        "hero_ok": "SCRUBBED",
        "hero_warn": "RESIDUAL METADATA",
        "hero_bad": "ERRORS",
        "hero_dry": "DRY RUN — NOTHING WRITTEN",
        "hero_sub_ok": "every file re-scanned clean",
        "hero_sub_warn": "some files still carry metadata — verify manually",
        "hero_sub_bad": "some files could not be processed",
        "res_title": "Per file",
        "filter_all": "all",
        "expand_all": "expand all",
        "collapse_all": "collapse all",
    },
    "tr": {
        "title": "MetaScrub raporu",
        "tagline": "Metadata temizliği — öncesi / sonrası",
        "generated": "Oluşturulma",
        "root": "Kaynak",
        "mode": "Mod",
        "mode_inplace": "yerinde (orijinaller değişti)",
        "mode_copy": "temizlenmiş kopyalar",
        "mode_dryrun": "deneme (hiçbir şey yazılmadı)",
        "sum_files": "Dosya",
        "sum_removed": "Silinen metadata alanı",
        "sum_residual": "Artık metadata kalan dosya",
        "sum_errors": "Hata",
        "col_field": "Alan",
        "col_namespace": "Grup",
        "col_before": "Eski değer",
        "kept": "Korunan (istek üzerine)",
        "residual": "Temizlik sonrası hâlâ duran — elle doğrulayın",
        "no_meta": "Metadata bulunamadı.",
        "out": "Çıktı",
        "size": "Boyut",
        "status_cleaned": "temizlendi",
        "status_skipped": "atlandı",
        "status_unsupported": "desteklenmiyor",
        "status_error": "hata",
        "would_remove": "Silinecek",
        "hero_ok": "TEMİZLENDİ",
        "hero_warn": "ARTIK METADATA VAR",
        "hero_bad": "HATA VAR",
        "hero_dry": "DENEME — HİÇBİR ŞEY YAZILMADI",
        "hero_sub_ok": "her dosya yeniden tarandı, temiz",
        "hero_sub_warn": "bazı dosyalarda hâlâ metadata var — elle doğrulayın",
        "hero_sub_bad": "bazı dosyalar işlenemedi",
        "res_title": "Dosya bazında",
        "filter_all": "tümü",
        "expand_all": "hepsini aç",
        "collapse_all": "hepsini kapat",
    },
}
