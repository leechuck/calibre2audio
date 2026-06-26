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
from . import library, tts
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


@app.command()
def generate(
    book: str = typer.Option(None, "--book", "-b", help="Title/author search."),
    book_id: int = typer.Option(None, "--book-id", help="Calibre book id."),
    file: str = typer.Option(None, "--file", help="Path to an ebook file."),
    from_phrase: str = typer.Option(
        None, "--from", "-f",
        help="A distinctive phrase you just read on the Kindle; narration "
             "starts here."),
    resume: bool = typer.Option(
        False, "--resume", "-r",
        help="Start where the previous export for this book ended."),
    minutes: float = typer.Option(
        60.0, "--minutes", "-m", help="Target length of audio, in minutes."),
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
):
    """Generate a single MP3 sized to your intended run length."""
    try:
        bk = library.resolve_book(book=book, book_id=book_id, file=file)
    except library.LibraryError as e:
        raise _fatal(str(e))

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
    elif from_phrase:
        try:
            start = find_phrase(text, from_phrase)
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


if __name__ == "__main__":
    app()
