#!/usr/bin/env python3
"""Package the Calibre plugin into an installable zip.

Calibre expects the plugin files at the *root* of the zip (not inside a
subfolder), including the empty `plugin-import-name-calibre2audio.txt` marker.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

ROOT = Path(__file__).parent
SRC = ROOT / "calibre-plugin"
OUT = ROOT / "dist" / "calibre2audio-plugin.zip"


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    files = sorted(
        p for p in SRC.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
    )
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            z.write(p, p.relative_to(SRC).as_posix())
    print(f"Wrote {OUT}  ({len(files)} files)")
    for p in files:
        print(f"  {p.relative_to(SRC).as_posix()}")


if __name__ == "__main__":
    main()
