"""Assemble synthesized audio chunks into a single tagged MP3.

Chunks are streamed into a temporary WAV via libsndfile (constant memory), then
encoded to MP3 with ffmpeg, carrying ID3 tags so the file shows up nicely in a
phone/watch player.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

import numpy as np
import soundfile as sf

from .tts import SAMPLE_RATE


@dataclass
class EncodeResult:
    out_path: Path
    duration_seconds: float


def _require_ffmpeg() -> str:
    found = shutil.which("ffmpeg")
    if not found:
        raise RuntimeError("ffmpeg not found on PATH; it is required to write MP3.")
    return found


def write_mp3(
    chunks: Iterable[np.ndarray],
    out_path: Path,
    *,
    title: str,
    artist: str,
    album: str,
    track: int | None = None,
    quality: int = 2,
    gap_seconds: float = 0.25,
) -> EncodeResult:
    """Stream ``chunks`` to ``out_path`` as MP3. Returns the final duration.

    A short silence is inserted between chunks so sentences don't run together.
    """
    ffmpeg = _require_ffmpeg()
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    gap = np.zeros(int(SAMPLE_RATE * gap_seconds), dtype=np.float32)
    total_samples = 0

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
        wav_path = Path(tf.name)
    try:
        with sf.SoundFile(
            str(wav_path), mode="w", samplerate=SAMPLE_RATE,
            channels=1, subtype="PCM_16",
        ) as wav:
            first = True
            for chunk in chunks:
                if chunk.size == 0:
                    continue
                if not first:
                    wav.write(gap)
                    total_samples += gap.size
                wav.write(chunk)
                total_samples += chunk.size
                first = False

        if total_samples == 0:
            raise RuntimeError("No audio was generated (empty text window?).")

        meta = ["-metadata", f"title={title}",
                "-metadata", f"artist={artist}",
                "-metadata", f"album={album}",
                "-metadata", "genre=Audiobook"]
        if track is not None:
            meta += ["-metadata", f"track={track}"]

        cmd = [ffmpeg, "-y", "-i", str(wav_path),
               "-codec:a", "libmp3lame", "-qscale:a", str(quality),
               *meta, str(out_path)]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg failed:\n{proc.stderr[-600:]}")
    finally:
        wav_path.unlink(missing_ok=True)

    return EncodeResult(out_path=out_path,
                        duration_seconds=total_samples / SAMPLE_RATE)
