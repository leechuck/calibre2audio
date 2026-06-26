"""Persistent state: where you left off in each book, and speech-rate calibration.

Everything lives under a single JSON file in the user data dir. Two kinds of
data are stored:

* ``books`` -- per-book resume info, keyed by a stable book key (Calibre id when
  available, else the absolute file path). Records the character offset in the
  normalised text where the last export ended, plus a snippet for sanity.
* ``calibration`` -- measured words-per-minute per (voice, speed), refined after
  every successful export so duration estimates get better over time.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path


def data_dir() -> Path:
    """Return the calibre2audio data directory, creating it if needed."""
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(
        os.path.expanduser("~"), ".local", "share"
    )
    d = Path(base) / "calibre2audio"
    d.mkdir(parents=True, exist_ok=True)
    return d


def cache_dir() -> Path:
    """Return the directory used to cache extracted plain text."""
    d = data_dir() / "textcache"
    d.mkdir(parents=True, exist_ok=True)
    return d


# Default speaking rate (words/minute) before any calibration exists.
# Kokoro at speed 1.0 lands around here for the English voices.
DEFAULT_WPM = 155.0


@dataclass
class Store:
    """Read/modify/write wrapper around the state JSON file."""

    path: Path
    _data: dict = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path | None = None) -> "Store":
        path = path or (data_dir() / "state.json")
        data: dict = {}
        if path.exists():
            try:
                data = json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                # Corrupt or unreadable state should never block a run; start fresh.
                data = {}
        data.setdefault("books", {})
        data.setdefault("calibration", {})
        return cls(path=path, _data=data)

    def save(self) -> None:
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self._data, indent=2, sort_keys=True))
        tmp.replace(self.path)

    # -- resume position -------------------------------------------------

    def get_resume(self, book_key: str) -> dict | None:
        return self._data["books"].get(book_key)

    def set_resume(self, book_key: str, *, end_offset: int, snippet: str,
                   title: str) -> None:
        self._data["books"][book_key] = {
            "end_offset": end_offset,
            "snippet": snippet,
            "title": title,
        }

    # -- wpm calibration -------------------------------------------------

    @staticmethod
    def _cal_key(voice: str, speed: float) -> str:
        return f"{voice}@{speed:g}"

    def get_wpm(self, voice: str, speed: float) -> float:
        rec = self._data["calibration"].get(self._cal_key(voice, speed))
        if rec and rec.get("wpm"):
            return float(rec["wpm"])
        # Speed scales rate roughly linearly off the default baseline.
        return DEFAULT_WPM * speed

    def update_wpm(self, voice: str, speed: float, measured_wpm: float) -> None:
        """Fold a freshly measured rate into a running average (EWMA)."""
        key = self._cal_key(voice, speed)
        rec = self._data["calibration"].get(key, {})
        prev = rec.get("wpm")
        n = int(rec.get("samples", 0))
        if prev is None:
            new = measured_wpm
        else:
            # Exponential moving average favouring recent measurements.
            alpha = 0.4
            new = (1 - alpha) * float(prev) + alpha * measured_wpm
        self._data["calibration"][key] = {"wpm": new, "samples": n + 1}
