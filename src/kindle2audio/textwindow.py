"""Find the start point in the text and carve out a run-length window.

Two jobs:

* ``find_phrase`` -- locate where in the book a phrase you just read on the
  Kindle occurs, tolerant of whitespace, case and punctuation differences, with
  a fuzzy fallback so a near-miss transcription still lands close.
* ``select_window`` -- starting from a character offset, take roughly ``target
  words`` worth of text, then extend to the next sentence/paragraph boundary so
  the audio never cuts off mid-thought.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

_WORD_RE = re.compile(r"\S+")
# Sentence end: ., !, ? optionally wrapped by quotes/brackets, then whitespace.
_SENT_END_RE = re.compile(r'[.!?]["”’\')\]]*\s')


@dataclass
class Window:
    start: int       # char offset into the full text where the slice begins
    end: int         # char offset where it ends (exclusive)
    text: str        # the sliced, narration-ready text
    word_count: int


def _norm(s: str) -> str:
    """Lowercase and collapse all runs of non-alphanumeric chars to one space."""
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def find_phrase(text: str, phrase: str) -> int:
    """Return the char offset in ``text`` where ``phrase`` starts.

    Raises ``ValueError`` if nothing close is found.
    """
    phrase = phrase.strip()
    if not phrase:
        raise ValueError("Empty start phrase.")

    # Fast path: exact case-insensitive match.
    idx = text.lower().find(phrase.lower())
    if idx != -1:
        return idx

    # Normalised match: build a map from normalised-char index back to the
    # original offset, then search the normalised haystack.
    norm_chars: list[str] = []
    back: list[int] = []
    prev_space = True
    for i, ch in enumerate(text):
        nc = ch.lower() if ch.isalnum() else " "
        if nc == " ":
            if prev_space:
                continue
            prev_space = True
        else:
            prev_space = False
        norm_chars.append(nc)
        back.append(i)
    norm_text = "".join(norm_chars)
    norm_phrase = _norm(phrase)
    pos = norm_text.find(norm_phrase)
    if pos != -1:
        return back[pos]

    # Fuzzy fallback: slide a window the size of the phrase across the
    # normalised text and keep the best-matching anchor.
    words = norm_phrase.split()
    if not words:
        raise ValueError("Start phrase has no searchable words.")
    anchor = words[0]
    best_ratio = 0.0
    best_off = -1
    start = 0
    while True:
        j = norm_text.find(anchor, start)
        if j == -1:
            break
        cand = norm_text[j:j + len(norm_phrase) + 20]
        ratio = SequenceMatcher(None, norm_phrase, cand).ratio()
        if ratio > best_ratio:
            best_ratio, best_off = ratio, back[j]
        start = j + 1
    if best_off != -1 and best_ratio >= 0.6:
        return best_off

    raise ValueError(
        "Could not find that phrase in the book. Try a longer, more distinctive "
        "snippet copied exactly as it appears."
    )


def select_window(text: str, start: int, target_words: int) -> Window:
    """Slice ~``target_words`` words from ``start``, ending on a clean boundary."""
    start = max(0, min(start, len(text)))
    if start >= len(text):
        return Window(start=start, end=start, text="", word_count=0)

    # Walk word matches from the start offset until we hit the target count.
    count = 0
    cut = len(text)
    for m in _WORD_RE.finditer(text, start):
        count += 1
        if count >= target_words:
            cut = m.end()
            break

    # Extend to the next sentence end so we don't stop mid-sentence.
    sent = _SENT_END_RE.search(text, cut)
    if sent:
        # Prefer a paragraph break shortly after, if one is close by.
        para = text.find("\n\n", cut, sent.end() + 400)
        cut = para if para != -1 else sent.end()
    else:
        cut = len(text)

    slice_text = text[start:cut].strip()
    return Window(
        start=start,
        end=cut,
        text=slice_text,
        word_count=len(_WORD_RE.findall(slice_text)),
    )
