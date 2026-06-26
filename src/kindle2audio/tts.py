"""Kokoro text-to-speech: stream a long text out as 24 kHz audio chunks.

Kokoro is loaded lazily (it drags in PyTorch) so the lightweight CLI commands
stay fast. The pipeline yields one audio chunk per text segment; we hand those
straight to the audio writer so memory stays flat regardless of book length.
"""

from __future__ import annotations

from typing import Callable, Iterator

import numpy as np

SAMPLE_RATE = 24000

# Curated, known-good English voices. Any other Kokoro voice id also works if
# passed explicitly; this list just drives `kindle2audio voices` and validation.
VOICES: dict[str, str] = {
    "af_heart": "American English, female (warm) — default",
    "af_bella": "American English, female",
    "af_nicole": "American English, female (soft/ASMR)",
    "af_sarah": "American English, female",
    "am_michael": "American English, male",
    "am_fenrir": "American English, male (deep)",
    "am_puck": "American English, male (bright)",
    "bf_emma": "British English, female",
    "bf_isabella": "British English, female",
    "bm_george": "British English, male",
    "bm_fable": "British English, male",
}


def resolve_device(device: str) -> str:
    """Map 'auto' to cuda when available, else cpu."""
    if device != "auto":
        return device
    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


def lang_code_for(voice: str) -> str:
    """Kokoro lang code is the voice prefix: 'a'=US English, 'b'=British, ..."""
    return voice[0] if voice else "a"


def _to_numpy(audio) -> np.ndarray:
    if isinstance(audio, np.ndarray):
        arr = audio
    else:  # torch tensor
        arr = audio.detach().cpu().numpy()
    return np.asarray(arr, dtype=np.float32).reshape(-1)


def synthesize(
    text: str,
    *,
    voice: str = "af_heart",
    speed: float = 1.0,
    device: str = "auto",
    progress: Callable[[int, int], None] | None = None,
) -> Iterator[np.ndarray]:
    """Yield float32 mono audio chunks (24 kHz) for ``text``.

    ``progress(done, total)`` is called after each chunk if supplied.
    """
    from kokoro import KPipeline

    dev = resolve_device(device)
    pipeline = KPipeline(lang_code=lang_code_for(voice), device=dev)

    # Pre-split exactly the way we ask Kokoro to, so progress totals are honest.
    split_pattern = r"\n+"
    import re
    segments = [s for s in re.split(split_pattern, text) if s.strip()]
    total = len(segments)

    done = 0
    for result in pipeline(
        text, voice=voice, speed=speed, split_pattern=split_pattern
    ):
        done += 1
        if progress:
            progress(done, total)
        # kokoro versions differ: a Result object with .audio, or a (gs, ps,
        # audio) tuple. Be tolerant of both, and skip phoneme-only segments.
        audio = getattr(result, "audio", None)
        if audio is None and isinstance(result, (tuple, list)):
            audio = result[-1]
        if audio is None:
            continue
        yield _to_numpy(audio)
