"""Lightweight self-test of the text pipeline (no TTS / no GPU needed)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from .devices import audio_files, parse_clippings, push, titles_match
from .textwindow import find_phrase, select_window

CLIPPINGS = (
    "﻿Nineteen Eighty-Four (Orwell, George)\n"
    "- Your Highlight on page 3 | Location 40-41 | Added on Monday, 1 June 2026\n"
    "\n"
    "the clocks were striking thirteen\n"
    "==========\n"
    "Emma (Austen, Jane)\n"
    "- Your Note on page 9 | Location 120 | Added on Tuesday, 2 June 2026\n"
    "\n"
    "my own note\n"
    "==========\n"
    "Emma (Austen, Jane)\n"
    "- Your Bookmark on page 9 | Location 120 | Added on Tuesday, 2 June 2026\n"
    "\n"
    "\n"
    "==========\n"
    "Emma (Austen, Jane)\n"
    "- Your Highlight on page 10 | Location 130 | Added on Tuesday, 2 June 2026\n"
    "\n"
    "Emma Woodhouse, handsome, clever, and rich\n"
    "==========\n"
)

SAMPLE = (
    "Chapter One\n\n"
    "It was a bright cold day in April, and the clocks were striking thirteen. "
    "Winston Smith, his chin nuzzled into his breast in an effort to escape the "
    "vile wind, slipped quickly through the glass doors of Victory Mansions, "
    "though not quickly enough to prevent a swirl of gritty dust from entering "
    "along with him.\n\n"
    "The hallway smelt of boiled cabbage and old rag mats. " * 50
)


def src_bytes(d: str) -> Path:
    p = Path(d) / "x.mp3"
    p.write_bytes(b"audio")
    return p


def main() -> None:
    # Exact, case- and whitespace-tolerant phrase search.
    off = find_phrase(SAMPLE, "the   CLOCKS were striking thirteen")
    assert SAMPLE[off:off + 10].lower().startswith("the clock"), off

    # Fuzzy fallback (a small transcription slip).
    off2 = find_phrase(SAMPLE, "clocks were strikin thirten")
    assert off2 > 0

    # Window selection snaps to a sentence boundary and respects the word target.
    win = select_window(SAMPLE, off, target_words=20)
    assert win.word_count >= 20
    assert win.text.rstrip().endswith((".", '."', '"'))

    # Kindle clippings: notes/bookmarks dropped, newest highlight per book.
    clips = parse_clippings(CLIPPINGS)
    assert [c.title for c in clips] == ["Nineteen Eighty-Four", "Emma"], clips
    assert clips[0].author == "Orwell, George"
    assert titles_match("Emma: A Novel", "Emma")

    # Suunto push: removable audio goes, non-music folders are left alone.
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "music" / "album").mkdir(parents=True)
        (root / "facdata").mkdir()
        (root / "facdata" / "cal.wav").write_bytes(b"x")
        (root / "music" / "old.mp3").write_bytes(b"x")
        (root / "music" / "album" / "older.flac").write_bytes(b"x")
        (root / "music" / "cover.jpg").write_bytes(b"x")
        src = Path(d) / "new.mp3"
        src.write_bytes(b"audio")
        res = push(src, root)
        assert res.dest == root / "music" / "new.mp3"
        assert audio_files(root / "music") == [res.dest]
        assert (root / "music" / "cover.jpg").exists()
        assert (root / "facdata" / "cal.wav").exists()

    # A volume without a music folder gets one (the device expects it).
    with tempfile.TemporaryDirectory() as d:
        assert push(src_bytes(d), Path(d)).dest.parent.name == "music"

    print("selftest OK")
    print(f"  phrase offset = {off}, fuzzy offset = {off2}")
    print(f"  window: {win.word_count} words, ends: …{win.text[-40:]!r}")


if __name__ == "__main__":
    main()
