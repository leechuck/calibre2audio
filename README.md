# calibre2audio

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
- [Loading the Suunto Aqua](#loading-the-suunto-aqua)
- [Duration accuracy & self-calibration](#duration-accuracy--self-calibration)
- [Voices](#voices)
- [Calibre plugin (GUI)](#calibre-plugin-gui)
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
git clone https://github.com/leechuck/calibre2audio.git
cd calibre2audio
uv sync          # or: just sync
```

The first synthesis run also downloads the Kokoro model weights (a few hundred
MB) once.

## Quick start

```sh
# Find a book's id / confirm the title
uv run calibre2audio books "hail mary"

# Generate ~90 minutes starting from a phrase you just read on the Kindle
uv run calibre2audio generate \
  --book "Project Hail Mary" \
  --from "the airlock cycled with a hiss" \
  --minutes 90

# Next run: continue from where that export ended
uv run calibre2audio generate --book "Project Hail Mary" --resume -m 60

# See where you'll resume from
uv run calibre2audio status --book "Project Hail Mary"

# The run-morning one-liner: highlight a sentence on the Kindle, plug in the
# Kindle and the Suunto Aqua, then render 1.5 h from that highlight and make it
# the only track on the headphones
uv run calibre2audio generate --from-highlight --hours 1.5 --to-suunto --eject
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
| `devices` | Show the connected Kindle (with its newest highlight) and Suunto Aqua. |
| `push <mp3>` | Make an existing MP3 the only removable track on the Suunto Aqua. |

Run `uv run calibre2audio --help` or `... <command> --help` for full details.

## Options for `generate`

| option | meaning |
| --- | --- |
| `--book, -b` | Title/author search to select the book. |
| `--book-id` | Select by exact Calibre id (avoids ambiguity). |
| `--file` | Use an ebook file directly, bypassing Calibre lookup. |
| `--from, -f` | Phrase to start at (your Kindle position). |
| `--from-highlight, -H` | Start at your newest highlight on the connected Kindle; also picks the book if none is given. |
| `--kindle` | Kindle mount path, if auto-detection misses it. |
| `--resume, -r` | Continue from the previous export's end instead of `--from`. |
| `--minutes, -m` | Target audio length in minutes (default 60). |
| `--hours, -t` | Target length in half-hour steps: 0.5, 1, 1.5, 2, 2.5 or 3. |
| `--to-suunto, -s` | Afterwards, wipe the Suunto Aqua's music folder and copy the MP3 there. |
| `--suunto` | Suunto mount path, if auto-detection misses it (or set `CALIBRE2AUDIO_SUUNTO`). |
| `--yes, -y` | Don't ask before deleting files from the Suunto. |
| `--eject` | Unmount the Suunto after copying. |
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

**`--from-highlight`** saves the typing. On the Kindle, long-press a sentence
on your current page and choose *Highlight*. The Kindle appends it to
`documents/My Clippings.txt`, which calibre2audio reads when the Kindle is
plugged in over USB. The newest highlight sets both the start point and, unless
you name one, the book (matched to Calibre by title, then author). Notes and
bookmarks are ignored. Newer Kindles connect over MTP: open the Kindle once in
the file manager so gvfs mounts it, or pass `--kindle PATH`. Run
`calibre2audio devices` to check what was found.

## Loading the Suunto Aqua

Put the headphones in their powerbank and connect it over USB-C; they mount as
a drive with a top-level `music` folder, which is what offline mode plays.
`--to-suunto` (or `push <mp3>` for an existing file) deletes every audio file in
that folder and copies the new MP3 in. It shows the files and asks first unless
you pass `--yes`, and it checks the headphones are connected *before* the long
render starts. The volume is found by a name containing "suunto" or "aqua";
otherwise pass `--suunto PATH` or set `CALIBRE2AUDIO_SUUNTO`.

The ten songs Suunto preloads cannot be removed: they are stored outside the
USB-visible drive and survive deleting its folders, and no custom firmware
exists. To hear only the audiobook, create a playlist in the Suunto app that
contains just your file and select it in offline mode.

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
uv run calibre2audio voices
```

Defaults to `af_heart` (warm American English female). The list includes several
American and British male/female voices; any other valid Kokoro voice id also
works via `--voice`. The voice prefix selects the accent model (`a` = American
English, `b` = British English).

## Calibre plugin (GUI)

Prefer to drive it from inside Calibre? There's a companion plugin that adds a
**Run audio** toolbar button. Select a book, click it, fill in a phrase (or pick
*Resume*) and a length, and it generates the MP3 in the background with a live
progress log. Optionally it attaches the MP3 back onto the book in your library.

The plugin is a thin front-end: Calibre's bundled Python can't host PyTorch, so
the plugin shells out to the `calibre2audio` CLI (which must be installed and on
your `PATH`). Install both like this:

```sh
just install-cli        # uv tool install . -> puts `calibre2audio` on PATH
just install-plugin     # builds dist/calibre2audio-plugin.zip and adds it to Calibre
# then restart Calibre
```

Or manually: `uv run python build_plugin.py` to build the zip, then in Calibre go
to **Preferences → Plugins → Load plugin from file** and pick
`dist/calibre2audio-plugin.zip`, then restart Calibre. If the **Run audio**
button doesn't appear, add it via **Preferences → Toolbars & menus → The main
toolbar**.

If the CLI isn't found, set its command (or absolute path) under **Preferences →
Plugins → Calibre2Audio → Customize plugin** — there you can also set a default
voice, length and output folder. The plugin can't read your Kindle position
either, so you still paste a phrase (or use *Resume*), exactly as with the CLI.

## Where state lives

Resume positions and words-per-minute calibration are stored under:

```
~/.local/share/calibre2audio/state.json      # per-book resume + calibration
~/.local/share/calibre2audio/textcache/      # cached extracted text
```

(Respects `XDG_DATA_HOME` if set.) Deleting these is harmless; you only lose
saved resume points and calibration.

## Project layout

```
src/calibre2audio/
  cli.py          Typer CLI: generate / books / voices / status
  library.py      Calibre lookup + text extraction (ebook-convert), cached
  textwindow.py   Phrase search (tolerant + fuzzy) and run-length windowing
  tts.py          Kokoro synthesis -> audio chunks
  audio.py        Stream chunks to a tagged MP3 via ffmpeg
  state.py        Resume positions + self-calibrating words-per-minute
  _selftest.py    Dependency-free check of the text pipeline

calibre-plugin/   Calibre GUI plugin (thin front-end that calls the CLI)
  __init__.py     InterfaceActionBase metadata
  ui.py           Toolbar action: read selected book, build & run the command
  dialog.py       Parameter dialog (phrase / resume, minutes, voice, …)
  jobs.py         Background subprocess worker + progress dialog
  config.py       Plugin preferences + config widget
build_plugin.py   Packages calibre-plugin/ into dist/calibre2audio-plugin.zip
```

A quick check of the text pipeline (no GPU/TTS needed):

```sh
just selftest        # or: uv run python -m calibre2audio._selftest
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
