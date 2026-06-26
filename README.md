# kindle2audio

Turn a stretch of a book in your [Calibre](https://calibre-ebook.com/) library
into a single MP3 sized to your run, starting from wherever you currently are on
your Kindle.

You read on the Kindle. When you want to keep going on a Zone 2 run or walk, you
hand this tool a phrase you just read plus a duration (say 90 minutes). It finds
that spot in the Calibre copy of the book, carves out roughly that much
listening, narrates it with a high-quality neural voice ([Kokoro](https://github.com/hexgrad/kokoro),
on your GPU when one is available), and drops a tagged MP3 you can sync to a
phone or watch. Next time, `--resume` picks up exactly where the last export
ended.

It is a small, self-contained command-line tool with no cloud dependency: text
extraction, synthesis and encoding all happen locally.

---

## Contents

- [Why](#why)
- [How it works](#how-it-works)
- [Requirements](#requirements)
- [Install](#install)
- [Quick start](#quick-start)
- [Commands](#commands)
- [Options](#options-for-generate)
- [Choosing where to start](#choosing-where-to-start)
- [Duration accuracy & self-calibration](#duration-accuracy--self-calibration)
- [Voices](#voices)
- [Where state lives](#where-state-lives)
- [Project layout](#project-layout)
- [Troubleshooting](#troubleshooting)
- [License](#license)

## Why

Audiobooks are great for running, but they are a separate purchase from the book
you are already reading, and they never start at *your* page. If you already own
the EPUB/PDF and read it on a Kindle, this bridges the gap: it narrates the next
chunk of *your* book, from *your* current spot, for *your* intended run length.

## How it works

1. **Find the book** in Calibre (`--book "title"`, `--book-id N`, or `--file path`).
2. **Extract text** via Calibre's own `ebook-convert` (handles EPUB and PDF
   uniformly), cached on disk so re-runs are instant.
3. **Locate your spot** by searching for a phrase you just read. The search is
   tolerant of whitespace, case and punctuation differences, with a fuzzy
   fallback so a small transcription slip still lands close.
4. **Size the window** to your run: `minutes × words-per-minute`, then extend to
   the next sentence/paragraph boundary so the audio never cuts off mid-thought.
   The words-per-minute rate self-calibrates from your actual outputs.
5. **Narrate** with Kokoro TTS (GPU when available, otherwise CPU) and **encode**
   a single tagged MP3 with `ffmpeg`.
6. **Remember** where it ended so `--resume` continues next time, with nothing
   lost or repeated.

## Requirements

- **Calibre** — provides `ebook-convert` and `calibredb` (your books should be in
  a Calibre library).
- **ffmpeg** — for MP3 encoding.
- **[uv](https://docs.astral.sh/uv/)** — to install and run the tool.
- **espeak-ng** *(recommended, optional)* — improves pronunciation of unusual or
  foreign words. Kokoro works without it.
  ```sh
  sudo apt install espeak-ng      # Debian/Ubuntu
  ```
- **NVIDIA GPU** *(optional)* — used automatically when available for fast
  synthesis. Without one it runs on CPU, which is slower but perfectly usable
  since you generate before the run, not during it.

The default install pulls a CUDA build of PyTorch (from the cu128 wheel index in
`pyproject.toml`), which works with recent NVIDIA drivers including the Blackwell
generation. If you have no NVIDIA GPU and want a smaller install, see
[Troubleshooting](#troubleshooting).

## Install

```sh
git clone https://github.com/leechuck/kindle2audio.git
cd kindle2audio
uv sync          # or: just sync
```

The first synthesis run also downloads the Kokoro model weights (a few hundred
MB) once.

## Quick start

```sh
# Find a book's id / confirm the title
uv run kindle2audio books "hail mary"

# Generate ~90 minutes starting from a phrase you just read on the Kindle
uv run kindle2audio generate \
  --book "Project Hail Mary" \
  --from "the airlock cycled with a hiss" \
  --minutes 90

# Next run: continue from where that export ended
uv run kindle2audio generate --book "Project Hail Mary" --resume -m 60

# See where you'll resume from
uv run kindle2audio status --book "Project Hail Mary"
```

Output lands in `~/audiobooks/` by default (`--out` to change). Files are tagged
with title/author/album so they group nicely in a player.

## Commands

| command | purpose |
| --- | --- |
| `generate` | Produce a single MP3 sized to your run length. |
| `books <query>` | List Calibre books matching a title/author search, with ids. |
| `voices` | List the curated Kokoro voices. |
| `status` | Show the saved resume position for a book. |

Run `uv run kindle2audio --help` or `... <command> --help` for full details.

## Options for `generate`

| option | meaning |
| --- | --- |
| `--book, -b` | Title/author search to select the book. |
| `--book-id` | Select by exact Calibre id (avoids ambiguity). |
| `--file` | Use an ebook file directly, bypassing Calibre lookup. |
| `--from, -f` | Phrase to start at (your Kindle position). |
| `--resume, -r` | Continue from the previous export's end instead of `--from`. |
| `--minutes, -m` | Target audio length in minutes (default 60). |
| `--voice, -v` | Kokoro voice (default `af_heart`; see `voices`). |
| `--speed` | Speech speed multiplier (1.0 = natural). |
| `--device` | `auto` (default) / `cuda` / `cpu`. |
| `--wpm` | Override the words-per-minute estimate. |
| `--out, -o` | Output directory (default `~/audiobooks`). |
| `--refresh` | Re-extract text, ignoring the cache. |

## Choosing where to start

You pick the start point with **`--from`**: copy a short, distinctive phrase you
just read on the Kindle (a full sentence works best) and paste it. The match is
case-, whitespace- and punctuation-insensitive, and if an exact match fails it
falls back to a fuzzy search, so a minor typo still lands you in the right place.

For subsequent runs of the same book, **`--resume`** is easier: it starts exactly
where the previous export finished. Use `--from` for the first export of a book
(or any time you skip around), `--resume` thereafter.

## Duration accuracy & self-calibration

The length you ask for is an estimate based on a speaking rate (words per
minute). The first export for a given voice/speed may be a few minutes off;
after each run the tool measures the *actual* rate and folds it into a running
average, so estimates tighten with use. You can also pin a rate with `--wpm`.

Crucially, **nothing is ever lost or repeated**: the exact character offset where
each export ends is saved, and `--resume` continues from precisely there
regardless of how the duration estimate landed.

## Voices

```sh
uv run kindle2audio voices
```

Defaults to `af_heart` (warm American English female). The list includes several
American and British male/female voices; any other valid Kokoro voice id also
works via `--voice`. The voice prefix selects the accent model (`a` = American
English, `b` = British English).

## Where state lives

Resume positions and words-per-minute calibration are stored under:

```
~/.local/share/kindle2audio/state.json      # per-book resume + calibration
~/.local/share/kindle2audio/textcache/      # cached extracted text
```

(Respects `XDG_DATA_HOME` if set.) Deleting these is harmless; you only lose
saved resume points and calibration.

## Project layout

```
src/kindle2audio/
  cli.py          Typer CLI: generate / books / voices / status
  library.py      Calibre lookup + text extraction (ebook-convert), cached
  textwindow.py   Phrase search (tolerant + fuzzy) and run-length windowing
  tts.py          Kokoro synthesis -> audio chunks
  audio.py        Stream chunks to a tagged MP3 via ffmpeg
  state.py        Resume positions + self-calibrating words-per-minute
  _selftest.py    Dependency-free check of the text pipeline
```

A quick check of the text pipeline (no GPU/TTS needed):

```sh
just selftest        # or: uv run python -m kindle2audio._selftest
```

## Troubleshooting

**`'ebook-convert'/'calibredb' not found`** — install Calibre and make sure its
CLI tools are on your `PATH`.

**`ffmpeg not found`** — install ffmpeg (`sudo apt install ffmpeg`).

**`'<book>' matched N books`** — narrow the search term or use `--book-id` (run
`books <query>` to see ids).

**`Could not find that phrase`** — copy a longer, more distinctive snippet
exactly as it appears on the Kindle; very short or very common phrases are
ambiguous.

**Mispronounced unusual words** — install `espeak-ng` (see Requirements).

**No NVIDIA GPU / want a smaller install** — synthesis falls back to CPU
automatically (`--device cpu` to force it). To avoid the large CUDA PyTorch
download entirely, install a CPU build of `torch` into the environment instead of
the pinned cu128 wheel (edit `[tool.uv.sources]` in `pyproject.toml` to drop the
`pytorch-cu128` index, or `uv pip install torch --index-url https://download.pytorch.org/whl/cpu`).

**Blackwell / very new GPU** — the pinned cu128 wheels include the needed
kernels; ensure your NVIDIA driver is recent enough (the CUDA 12.8 runtime is
bundled in the wheel, so only a compatible driver is required).

## License

[MIT](LICENSE) © 2026 Robert Hoehndorf.

This tool uses [Kokoro](https://github.com/hexgrad/kokoro) (Apache-2.0) for
speech synthesis and [Calibre](https://calibre-ebook.com/) for ebook
conversion; those carry their own licenses.
