from __future__ import annotations

import fnmatch
import os


def iter_files(
    roots: list[str],
    filetypes: list[str],
    *,
    recursive: bool = True,
    exclude: list[str] | None = None,
    follow_symlinks: bool = True,
) -> list[str]:
    """Expand a mix of file and directory paths into a sorted, deduplicated
    list of files whose extension is in `filetypes`.

    A path given directly on the command line is always included regardless
    of `filetypes` (the user pointed at it on purpose); the extension
    filter, `exclude` globs and `follow_symlinks` only apply when walking
    into a directory.

    `exclude` globs are matched against both the bare name and the path
    relative to the walk root, so `*.tmp`, `drafts/*` and `*/cache/*` all
    work; a matching directory is pruned, not just its files.
    """
    wanted = {ft.lower().lstrip(".") for ft in filetypes if ft.strip()}
    patterns = [p for p in (exclude or []) if p]
    found: list[str] = []
    seen: set[str] = set()

    def add(path: str) -> None:
        real = os.path.realpath(path)
        if real not in seen and os.path.isfile(path):
            seen.add(real)
            found.append(path)

    def excluded(rel: str, name: str) -> bool:
        return any(
            fnmatch.fnmatch(name, pat) or fnmatch.fnmatch(rel, pat) for pat in patterns
        )

    for root in roots:
        if os.path.isfile(root):
            add(root)
        elif os.path.isdir(root):
            if recursive:
                for dirpath, dirnames, names in os.walk(root, followlinks=follow_symlinks):
                    rel_dir = os.path.relpath(dirpath, root)
                    if patterns:
                        dirnames[:] = [
                            d for d in dirnames
                            if not excluded(os.path.normpath(os.path.join(rel_dir, d)), d)
                        ]
                    for name in names:
                        if _ext(name) not in wanted:
                            continue
                        full = os.path.join(dirpath, name)
                        rel = os.path.normpath(os.path.join(rel_dir, name))
                        if patterns and excluded(rel, name):
                            continue
                        if not follow_symlinks and os.path.islink(full):
                            continue
                        add(full)
            else:
                for name in sorted(os.listdir(root)):
                    full = os.path.join(root, name)
                    if _ext(name) not in wanted or not os.path.isfile(full):
                        continue
                    if patterns and excluded(name, name):
                        continue
                    if not follow_symlinks and os.path.islink(full):
                        continue
                    add(full)
        # non-existent paths are silently ignored here; the caller reports them

    found.sort()
    return found


def _ext(name: str) -> str:
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""
