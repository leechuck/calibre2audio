"""Command-line interface for calibre2audio."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import typer
from rich.console import Console
from rich.progress import (BarColumn, Progress, TaskProgressColumn, TextColumn,
                           TimeElapsedColumn)
from rich.table import Table

from . import audio as audio_mod
from . import devices, library, tts
from .state import Store
from .textwindow import find_phrase, select_window

app = typer.Typer(
    add_completion=False,
    help="Turn a stretch of a Calibre book into a run-length MP3, starting "
         "from where you are on your Kindle.",
    no_args_is_help=True,
)
console = Console()
err = Console(stderr=True)


def _fatal(msg: str) -> "typer.Exit":
    err.print(f"[bold red]error:[/] {msg}")
    return typer.Exit(code=1)


def _safe_filename(name: str) -> str:
    name = re.sub(r"[^\w\s.\-\[\]+]", "", name).strip()
    return re.sub(r"\s+", " ", name) or "audio"


# Run lengths offered for --hours: half-hour steps up to three hours.
HOUR_STEPS = (0.5, 1.0, 1.5, 2.0, 2.5, 3.0)


def _confirm_wipe(root: Path, yes: bool) -> None:
    """Show what will be deleted from the headphones and ask before going on."""
    files = devices.audio_files(devices.music_dir(root))
    console.print(f"Suunto Aqua at [bold]{root}[/]")
    if not files:
        console.print("  no audio files to remove")
        return
    console.print(f"  will delete {len(files)} audio file(s):")
    for f in files[:15]:
        console.print(f"    [dim]{f.relative_to(root)}[/]")
    if len(files) > 15:
        console.print(f"    [dim]… and {len(files) - 15} more[/]")
    if not yes and not typer.confirm("Delete these and load the new MP3?"):
        raise typer.Exit(code=1)


def _push(mp3: Path, root: Path, eject: bool) -> None:
    with console.status("Copying to the headphones…"):
        try:
            res = devices.push(mp3, root)
        except devices.DeviceError as e:
            raise _fatal(str(e))
    console.print(f"[bold green]✓[/] on headphones: {res.dest} "
                  f"(removed {len(res.removed)} file(s))")
    if res.protected:
        console.print(f"[yellow]{len(res.protected)} file(s) could not be "
                      f"deleted:[/]")
        for f, why in res.protected:
            console.print(f"    [dim]{f.relative_to(root)}: {why}[/]")
    console.print("[dim]The 10 preloaded songs live outside the USB drive and "
                  "can't be removed; select a playlist with just this file in "
                  "the Suunto app to hear only the audiobook.[/]")
    if eject:
        problem = devices.eject(root)
        if problem:
            console.print(f"[yellow]Could not unmount:[/] {problem}")
        else:
            console.print("Unmounted; safe to unplug.")


def _fmt_dur(seconds: float) -> str:
    m, s = divmod(int(round(seconds)), 60)
    h, m = divmod(m, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:d}:{s:02d}"


@app.command()
def books(query: str = typer.Argument(..., help="Title/author search term.")):
    """List Calibre books matching a search term (with their ids)."""
    try:
        matches = library.find_books(query)
    except library.LibraryError as e:
        raise _fatal(str(e))
    if not matches:
        console.print(f"No books matched [bold]{query}[/].")
        raise typer.Exit()
    table = Table(show_header=True, header_style="bold")
    table.add_column("id", justify="right")
    table.add_column("title")
    table.add_column("author")
    table.add_column("fmt")
    for b in matches:
        table.add_row(b.key.split(":")[-1], b.title, b.authors, b.fmt)
    console.print(table)


@app.command()
def voices():
    """List the curated Kokoro voices."""
    table = Table(show_header=True, header_style="bold")
    table.add_column("voice")
    table.add_column("description")
    for name, desc in tts.VOICES.items():
        table.add_row(name, desc)
    console.print(table)
    console.print("\n[dim]Any other Kokoro voice id also works via --voice.[/]")


@app.command()
def status(
    book: str = typer.Option(None, "--book", "-b", help="Title/author search."),
    book_id: int = typer.Option(None, "--book-id", help="Calibre book id."),
    file: str = typer.Option(None, "--file", help="Path to an ebook file."),
):
    """Show the saved resume position for a book."""
    try:
        bk = library.resolve_book(book=book, book_id=book_id, file=file)
    except library.LibraryError as e:
        raise _fatal(str(e))
    store = Store.load()
    rec = store.get_resume(bk.key)
    if not rec:
        console.print(f"No saved position for [bold]{bk.title}[/] yet.")
        raise typer.Exit()
    text = library.extract_text(bk)
    pct = 100 * rec["end_offset"] / max(1, len(text))
    console.print(f"[bold]{bk.title}[/] — resume at ~{pct:.0f}% through the book")
    console.print(f"  last ended near: [italic]…{rec['snippet']}[/]")


@app.command(name="devices")
def show_devices(
    kindle: str = typer.Option(None, "--kindle", help="Kindle mount path."),
    suunto: str = typer.Option(None, "--suunto", help="Suunto mount path."),
):
    """Show the connected Kindle (with its newest highlight) and Suunto Aqua."""
    try:
        clips = devices.find_kindle_clippings(kindle)
        c = devices.latest_highlight(clips)
        console.print(f"Kindle: [bold]{clips}[/]\n  newest highlight: "
                      f"[bold]{c.title}[/] ({c.author})\n  "
                      f"[italic]“{c.text[:100]}”[/]")
    except devices.DeviceError as e:
        console.print(f"Kindle: [yellow]{e}[/]")
    try:
        root = devices.find_suunto(suunto)
        folder = devices.music_dir(root)
        files = devices.audio_files(folder)
        console.print(f"Suunto: [bold]{root}[/] (music folder: {folder})")
        for f in files:
            console.print(f"  [dim]{f.relative_to(root)}[/]")
    except devices.DeviceError as e:
        console.print(f"Suunto: [yellow]{e}[/]")


@app.command()
def push(
    mp3: Path = typer.Argument(..., exists=True, dir_okay=False,
                               help="MP3 to load."),
    suunto: str = typer.Option(None, "--suunto", help="Suunto mount path."),
    yes: bool = typer.Option(False, "--yes", "-y",
                             help="Don't ask before deleting."),
    eject: bool = typer.Option(False, "--eject",
                               help="Unmount the headphones afterwards."),
):
    """Make MP3 the only removable track on the Suunto Aqua."""
    try:
        root = devices.find_suunto(suunto)
    except devices.DeviceError as e:
        raise _fatal(str(e))
    _confirm_wipe(root, yes)
    _push(mp3, root, eject)


@app.command()
def generate(
    book: str = typer.Option(None, "--book", "-b", help="Title/author search."),
    book_id: int = typer.Option(None, "--book-id", help="Calibre book id."),
    file: str = typer.Option(None, "--file", help="Path to an ebook file."),
    from_phrase: str = typer.Option(
        None, "--from", "-f",
        help="A distinctive phrase you just read on the Kindle; narration "
             "starts here."),
    from_highlight: bool = typer.Option(
        False, "--from-highlight", "-H",
        help="Start at your newest highlight on the connected Kindle. Also "
             "picks the book from it if no --book/--book-id/--file is given."),
    kindle: str = typer.Option(
        None, "--kindle", help="Kindle mount path (default: auto-detect)."),
    resume: bool = typer.Option(
        False, "--resume", "-r",
        help="Start where the previous export for this book ended."),
    minutes: float = typer.Option(
        60.0, "--minutes", "-m", help="Target length of audio, in minutes."),
    hours: float = typer.Option(
        None, "--hours", "-t",
        help="Target length in hours: 0.5, 1, 1.5, 2, 2.5 or 3 "
             "(overrides --minutes)."),
    to_suunto: bool = typer.Option(
        False, "--to-suunto", "-s",
        help="Afterwards, make the MP3 the only removable track on the "
             "connected Suunto Aqua."),
    suunto: str = typer.Option(
        None, "--suunto", help="Suunto mount path (default: auto-detect)."),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Don't ask before deleting from the Suunto."),
    eject: bool = typer.Option(
        False, "--eject", help="Unmount the Suunto after copying."),
    voice: str = typer.Option("af_heart", "--voice", "-v", help="Kokoro voice."),
    speed: float = typer.Option(1.0, "--speed", help="Speech speed multiplier."),
    out: Path = typer.Option(
        Path("~/audiobooks").expanduser(), "--out", "-o",
        help="Output directory for the MP3."),
    device: str = typer.Option(
        "auto", "--device", help="auto | cuda | cpu."),
    wpm: float = typer.Option(
        None, "--wpm",
        help="Override words-per-minute estimate (else self-calibrated)."),
    refresh: bool = typer.Option(
        False, "--refresh", help="Re-extract text, ignoring the cache."),
    title: str = typer.Option(
        None, "--title",
        help="Override the book title used for tags/filename (e.g. from "
             "Calibre metadata when using --file)."),
    author: str = typer.Option(
        None, "--author", help="Override the author used for tags."),
    print_path: bool = typer.Option(
        False, "--print-path",
        help="On success, print 'OUTPUT_PATH\\t<file>' as the last line "
             "(for scripting / the Calibre plugin)."),
):
    """Generate a single MP3 sized to your intended run length."""
    if hours is not None:
        if hours not in HOUR_STEPS:
            raise _fatal("--hours must be one of "
                         + ", ".join(f"{h:g}" for h in HOUR_STEPS) + ".")
        minutes = hours * 60
    if sum(map(bool, (from_phrase, from_highlight, resume))) > 1:
        raise _fatal("Use only one of --from, --from-highlight, --resume.")

    # Check the headphones are there (and agree the wipe) before the long
    # render, so you can walk away once it starts.
    suunto_root = None
    if to_suunto:
        try:
            suunto_root = devices.find_suunto(suunto)
        except devices.DeviceError as e:
            raise _fatal(str(e))
        _confirm_wipe(suunto_root, yes)

    have_selector = bool(book or book_id is not None or file)
    clip = None
    try:
        if from_highlight:
            clips_path = devices.find_kindle_clippings(kindle)
            if have_selector:
                bk = library.resolve_book(book=book, book_id=book_id, file=file)
                clip = devices.latest_highlight(clips_path, title or bk.title)
            else:
                clip = devices.latest_highlight(clips_path)
                bk = library.resolve_by_title(clip.title, clip.author)
            console.print(f"Newest highlight: [italic]“{clip.text[:80]}”[/]")
        else:
            bk = library.resolve_book(book=book, book_id=book_id, file=file)
    except (library.LibraryError, devices.DeviceError) as e:
        raise _fatal(str(e))

    # Let callers override metadata (the Calibre plugin passes --file plus the
    # library's real title/author so tags are correct).
    if title:
        bk.title = title
    if author:
        bk.authors = author

    console.print(f"[bold]{bk.title}[/] — {bk.authors}  [dim]({bk.fmt})[/]")
    with console.status("Extracting text…"):
        try:
            text = library.extract_text(bk, refresh=refresh)
        except library.LibraryError as e:
            raise _fatal(str(e))
    if not text.strip():
        raise _fatal("No readable text could be extracted from this book.")

    store = Store.load()

    # -- determine the start offset --------------------------------------
    if resume:
        rec = store.get_resume(bk.key)
        if not rec:
            raise _fatal("No saved position to resume from; use --from for the "
                         "first export of this book.")
        start = int(rec["end_offset"])
        if start >= len(text):
            raise _fatal("Saved position is at the end of the book — nothing "
                         "left to narrate.")
    elif from_phrase or clip:
        # A long highlight only slows the fuzzy search; its opening is enough.
        phrase = from_phrase or " ".join(clip.text.split()[:15])
        try:
            start = find_phrase(text, phrase)
        except ValueError as e:
            raise _fatal(str(e))
    else:
        console.print("[yellow]No --from or --resume given; starting at the "
                      "beginning of the book.[/]")
        start = 0

    # -- size the window -------------------------------------------------
    rate = wpm if wpm else store.get_wpm(voice, speed)
    target_words = max(1, int(minutes * rate))
    win = select_window(text, start, target_words)
    if win.word_count == 0:
        raise _fatal("Selected window is empty (already at end of book?).")

    start_pct = 100 * win.start / len(text)
    est_minutes = win.word_count / max(rate, 1e-6)
    preview = re.sub(r"\s+", " ", win.text[:90]).strip()
    console.print(
        f"Start ~{start_pct:.0f}% in · {win.word_count:,} words · "
        f"~{est_minutes:.0f} min estimated\n[dim]opening: “{preview}…”[/]")

    if voice not in tts.VOICES:
        console.print(f"[yellow]Note:[/] '{voice}' is not in the curated list; "
                      f"trying it anyway.")
    if shutil.which("espeak-ng") is None:
        console.print("[dim]Tip: install 'espeak-ng' for best pronunciation of "
                      "unusual/foreign words.[/]")

    dev = tts.resolve_device(device)
    console.print(f"Synthesizing with [bold]{voice}[/] on [bold]{dev}[/]…")

    # -- synthesize & encode --------------------------------------------
    fname = _safe_filename(f"{bk.title} [{start_pct:.0f}pct +{minutes:g}min]") + ".mp3"
    out_path = out / fname
    n = 1
    while out_path.exists():
        out_path = out / (_safe_filename(
            f"{bk.title} [{start_pct:.0f}pct +{minutes:g}min] ({n})") + ".mp3")
        n += 1

    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(), TaskProgressColumn(), TimeElapsedColumn(),
        console=console,
    ) as prog:
        task = prog.add_task("Narrating", total=None)

        def cb(done: int, total: int) -> None:
            prog.update(task, total=total, completed=done)

        chunks = tts.synthesize(
            win.text, voice=voice, speed=speed, device=device, progress=cb)
        try:
            result = audio_mod.write_mp3(
                chunks, out_path,
                title=f"{bk.title} (from {start_pct:.0f}%)",
                artist=bk.authors, album=bk.title)
        except RuntimeError as e:
            raise _fatal(str(e))

    # -- record progress + calibrate -------------------------------------
    measured_wpm = win.word_count / max(result.duration_seconds / 60, 1e-6)
    store.update_wpm(voice, speed, measured_wpm)
    snippet = re.sub(r"\s+", " ", win.text[-80:]).strip()
    store.set_resume(bk.key, end_offset=win.end, snippet=snippet, title=bk.title)
    store.save()

    console.print(
        f"\n[bold green]✓[/] {out_path}\n"
        f"  {_fmt_dur(result.duration_seconds)} of audio "
        f"({measured_wpm:.0f} wpm measured) · resume saved at "
        f"~{100*win.end/len(text):.0f}%")

    if suunto_root is not None:
        _push(out_path, suunto_root, eject)

    if print_path:
        # Plain, unformatted, stable last line for machine consumption.
        print(f"OUTPUT_PATH\t{out_path.resolve()}")


if __name__ == "__main__":
    app()
