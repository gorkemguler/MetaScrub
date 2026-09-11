"""Compare two `metacls clean` runs — what's new, what's gone, and which
files had metadata *reappear* (someone re-saved them in an editor)."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field


@dataclass
class RunDiff:
    new_files: list[str] = field(default_factory=list)          # in B, not in A
    removed_files: list[str] = field(default_factory=list)      # in A, not in B
    regained: dict[str, list[str]] = field(default_factory=dict)  # file -> fields scrubbed in B but not A
    cleared: dict[str, list[str]] = field(default_factory=dict)   # file -> fields scrubbed in A but not B
    residual_new: dict[str, list[str]] = field(default_factory=dict)  # file -> residual present in B, not A

    @property
    def any_changes(self) -> bool:
        return bool(self.new_files or self.removed_files or self.regained
                    or self.cleared or self.residual_new)


def load_report(path: str) -> dict:
    """Accept a report.json file or a run directory containing one."""
    if os.path.isdir(path):
        path = os.path.join(path, "report.json")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def diff_reports(report_a: dict, report_b: dict) -> RunDiff:
    a = _by_file(report_a)
    b = _by_file(report_b)
    out = RunDiff(
        new_files=sorted(set(b) - set(a)),
        removed_files=sorted(set(a) - set(b)),
    )
    for name in sorted(set(a) & set(b)):
        fa, fb = a[name], b[name]
        regained = sorted(fb["removed"] - fa["removed"])
        cleared = sorted(fa["removed"] - fb["removed"])
        residual_new = sorted(fb["residual"] - fa["residual"])
        if regained:
            out.regained[name] = regained
        if cleared:
            out.cleared[name] = cleared
        if residual_new:
            out.residual_new[name] = residual_new
    return out


def _by_file(report: dict) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for f in report.get("files", []):
        key = os.path.basename(f.get("src_path", "")) or "<unknown>"
        out[key] = {
            "removed": {f"{r['namespace']}:{r['field']}" for r in f.get("removed", [])},
            "residual": set(f.get("residual", [])),
        }
    return out
