"""Lightweight self-test of the text pipeline (no TTS / no GPU needed)."""

from __future__ import annotations

from .textwindow import find_phrase, select_window

SAMPLE = (
    "Chapter One\n\n"
    "It was a bright cold day in April, and the clocks were striking thirteen. "
    "Winston Smith, his chin nuzzled into his breast in an effort to escape the "
    "vile wind, slipped quickly through the glass doors of Victory Mansions, "
    "though not quickly enough to prevent a swirl of gritty dust from entering "
    "along with him.\n\n"
    "The hallway smelt of boiled cabbage and old rag mats. " * 50
)


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

    print("selftest OK")
    print(f"  phrase offset = {off}, fuzzy offset = {off2}")
    print(f"  window: {win.word_count} words, ends: …{win.text[-40:]!r}")


if __name__ == "__main__":
    main()
