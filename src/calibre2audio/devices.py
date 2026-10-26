"""USB devices: read the newest highlight off a Kindle, and load the Suunto Aqua.

Both devices show up as mounted volumes. A Kindle is either USB mass storage
(older models, auto-mounted under ``/media/$USER``) or MTP (newer models, which
GNOME exposes through gvfs under ``/run/user/$UID/gvfs``). We search both and
treat whatever we find as a plain directory tree.

Kindle: every highlight is appended to ``documents/My Clippings.txt``, so the
last highlight entry in that file is the one you just made.

Suunto Aqua: in its powerbank, connected over USB-C, the headphones appear as a
drive with a top-level ``music`` folder (files go directly in it, no
subfolders); offline mode plays what is in there. The ten preloaded songs are
stored elsewhere on the device, invisible over USB, and cannot be deleted; to
hear only the audiobook, pick a playlist with just that file in the Suunto app.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


class DeviceError(RuntimeError):
    """Raised for any user-facing problem finding or using a device."""


# Formats the Suunto Aqua plays in offline mode (per Suunto's user guide).
AUDIO_EXTS = {".mp3", ".flac", ".wav", ".aac", ".m4a", ".ape", ".wma"}

# Folders on a FAT volume that are filesystem/OS housekeeping, never music.
_SKIP_DIRS = {"system volume information", "$recycle.bin", "lost+found",
              "facdata"}


def _mount_roots() -> list[Path]:
    """Directories that hold auto-mounted removable volumes (incl. MTP via gvfs)."""
    user = os.environ.get("USER") or Path.home().name
    roots = [Path("/media") / user, Path("/run/media") / user, Path("/media"),
             Path(f"/run/user/{os.getuid()}/gvfs")]
    return [r for r in roots if r.is_dir()]


def _volumes() -> list[Path]:
    """Each mounted volume, plus its first level for MTP ("Internal Storage")."""
    vols: list[Path] = []
    for root in _mount_roots():
        try:
            children = [c for c in root.iterdir() if c.is_dir()]
        except OSError:
            continue
        for c in children:
            vols.append(c)
            if c.name.startswith("mtp:"):
                try:
                    vols.extend(s for s in c.iterdir() if s.is_dir())
                except OSError:
                    pass
    return vols


# ---------------------------------------------------------------------------
# Kindle
# ---------------------------------------------------------------------------

@dataclass
class Clipping:
    title: str
    author: str
    text: str


def find_kindle_clippings(kindle: str | None = None) -> Path:
    """Return the path of ``My Clippings.txt`` on the connected Kindle."""
    candidates = [Path(kindle).expanduser()] if kindle else _volumes()
    for vol in candidates:
        for rel in ("documents/My Clippings.txt", "My Clippings.txt"):
            p = vol / rel
            if p.is_file():
                return p
    if kindle:
        raise DeviceError(f"No 'documents/My Clippings.txt' under {kindle}.")
    raise DeviceError(
        "No Kindle found. Plug it in over USB and unlock it (newer Kindles "
        "show up as MTP; open it once in the file manager so it mounts), or "
        "pass --kindle PATH.")


def parse_clippings(raw: str) -> list[Clipping]:
    """Parse ``My Clippings.txt`` into highlights, oldest first.

    Notes (your own text) and bookmarks (no text) are dropped: only highlights
    contain words from the book.
    """
    out: list[Clipping] = []
    for entry in raw.replace("﻿", "").split("=========="):
        lines = [ln.strip() for ln in entry.strip().splitlines()]
        if len(lines) < 3:
            continue
        head, meta, body = lines[0], lines[1], " ".join(lines[2:]).strip()
        if not body or re.search(r"\b(note|bookmark|notiz|lesezeichen)\b",
                                 meta, re.I):
            continue
        m = re.match(r"^(.*)\s+\(([^()]*)\)\s*$", head)
        title, author = (m.group(1), m.group(2)) if m else (head, "")
        out.append(Clipping(title=title.strip(), author=author.strip(),
                            text=body))
    return out


def _title_key(s: str) -> str:
    # Drop subtitles and series suffixes; Kindle and Calibre often differ there.
    s = re.split(r"[:(\[]", s, maxsplit=1)[0]
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def titles_match(a: str, b: str) -> bool:
    ka, kb = _title_key(a), _title_key(b)
    return bool(ka and kb) and (ka in kb or kb in ka)


def latest_highlight(path: Path, title: str | None = None) -> Clipping:
    """Newest highlight, optionally restricted to a book title."""
    clips = parse_clippings(path.read_text(encoding="utf-8", errors="replace"))
    if title:
        clips = [c for c in clips if titles_match(c.title, title)]
    if not clips:
        where = f" for '{title}'" if title else ""
        raise DeviceError(
            f"No highlights{where} in {path}. On the Kindle, long-press a "
            f"sentence on your current page and choose Highlight.")
    return clips[-1]


# ---------------------------------------------------------------------------
# Suunto Aqua
# ---------------------------------------------------------------------------

def find_suunto(suunto: str | None = None) -> Path:
    """Return the root of the mounted Suunto Aqua volume."""
    if suunto:
        p = Path(suunto).expanduser()
        if not p.is_dir():
            raise DeviceError(f"Not a directory: {p}")
        return p
    env = os.environ.get("CALIBRE2AUDIO_SUUNTO")
    if env and Path(env).is_dir():
        return Path(env)
    hits = [v for v in _volumes() if re.search(r"suunto|aqua", v.name, re.I)]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        listing = "\n".join(f"  - {h}" for h in hits)
        raise DeviceError(f"Several possible Suunto volumes; pass --suunto:\n"
                          f"{listing}")
    raise DeviceError(
        "No Suunto Aqua found. Put the headphones in the powerbank, connect it "
        "by USB-C, and check it is mounted. If it mounts under an unexpected "
        "name, pass --suunto PATH or set CALIBRE2AUDIO_SUUNTO.")


def music_dir(root: Path) -> Path:
    """The top-level ``music`` folder offline mode plays from (created if absent)."""
    try:
        for c in root.iterdir():
            if c.is_dir() and c.name.lower() == "music":
                return c
        (root / "music").mkdir()
    except OSError as e:
        raise DeviceError(f"Cannot use {root}: {e}") from e
    return root / "music"


def audio_files(folder: Path) -> list[Path]:
    """All audio files under ``folder``, skipping hidden and system dirs."""
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(folder):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")
                       and d.lower() not in _SKIP_DIRS]
        for f in filenames:
            if not f.startswith(".") and Path(f).suffix.lower() in AUDIO_EXTS:
                found.append(Path(dirpath) / f)
    return sorted(found)


@dataclass
class PushResult:
    dest: Path
    removed: list[Path]
    protected: list[tuple[Path, str]]   # files the device refused to delete


def push(mp3: Path, root: Path) -> PushResult:
    """Delete every removable audio file on the headphones, then copy ``mp3``.

    Files the device refuses to delete are left in place and reported.
    """
    folder = music_dir(root)
    removed: list[Path] = []
    protected: list[tuple[Path, str]] = []
    for f in audio_files(folder):
        try:
            f.unlink()
            removed.append(f)
        except OSError as e:
            protected.append((f, e.strerror or str(e)))

    try:
        free = shutil.disk_usage(folder).free
    except OSError:
        free = None   # some MTP mounts don't report usage; just try the copy
    if free is not None and free < mp3.stat().st_size:
        raise DeviceError(
            f"Not enough space on the headphones ({free / 1e6:.0f} MB free, "
            f"{mp3.stat().st_size / 1e6:.0f} MB needed).")

    dest = folder / mp3.name
    # Copy under a non-audio name and rename, so an interrupted copy never
    # leaves a truncated MP3 for offline mode to play. gvfs MTP mounts can't
    # always rename, so there we write the final name directly.
    tmp = dest if "/gvfs/" in str(dest) else dest.with_name(dest.name + ".part")
    try:
        # copyfile, not copy2: FAT and MTP mounts reject most metadata calls.
        shutil.copyfile(mp3, tmp)
        if tmp != dest:
            tmp.rename(dest)
    except OSError as e:
        tmp.unlink(missing_ok=True)
        raise DeviceError(f"Copy to {dest} failed: {e}") from e
    os.sync()
    return PushResult(dest=dest, removed=removed, protected=protected)


def eject(root: Path) -> str | None:
    """Unmount the volume so it's safe to unplug; return an error or None."""
    gio = shutil.which("gio")
    if not gio:
        return "'gio' not found; unmount it from the file manager."
    r = subprocess.run([gio, "mount", "-u", str(root)],
                       capture_output=True, text=True)
    return None if r.returncode == 0 else (r.stderr.strip() or "unmount failed")
