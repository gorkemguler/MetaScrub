from __future__ import annotations

import os


def iter_files(roots: list[str], filetypes: list[str], *, recursive: bool = True) -> list[str]:
    """Expand a mix of file and directory paths into a sorted, deduplicated
    list of files whose extension is in `filetypes`.

    A path given directly on the command line is always included regardless
    of `filetypes` (the user pointed at it on purpose); the extension
    filter only applies when walking into a directory.
    """
    wanted = {ft.lower().lstrip(".") for ft in filetypes if ft.strip()}
    found: list[str] = []
    seen: set[str] = set()

    def add(path: str) -> None:
        real = os.path.realpath(path)
        if real not in seen and os.path.isfile(path):
            seen.add(real)
            found.append(path)

    for root in roots:
        if os.path.isfile(root):
            add(root)
        elif os.path.isdir(root):
            if recursive:
                for dirpath, _, names in os.walk(root):
                    for name in names:
                        if _ext(name) in wanted:
                            add(os.path.join(dirpath, name))
            else:
                for name in os.listdir(root):
                    full = os.path.join(root, name)
                    if os.path.isfile(full) and _ext(name) in wanted:
                        add(full)
        # non-existent paths are silently ignored here; the caller reports them

    found.sort()
    return found


def _ext(name: str) -> str:
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""
