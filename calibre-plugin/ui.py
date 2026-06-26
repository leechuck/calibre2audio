"""Toolbar action: collect the selected book + parameters, run the CLI."""

import os
import shlex
import shutil

from qt.core import QDialog, QIcon

from calibre.gui2 import error_dialog, info_dialog
from calibre.gui2.actions import InterfaceAction

from calibre_plugins.calibre2audio.config import prefs
from calibre_plugins.calibre2audio.dialog import GenerateDialog, resume_info
from calibre_plugins.calibre2audio.jobs import ProgressDialog

# Formats calibre2audio can read, best first.
_FORMAT_ORDER = ["EPUB", "AZW3", "MOBI", "PDF", "TXT"]


class InterfacePlugin(InterfaceAction):

    name = "Calibre2Audio"
    # (text, icon, tooltip, keyboard shortcut)
    action_spec = ("Run audio", None,
                   "Generate a run-length MP3 from this book", None)
    action_type = "current"

    def genesis(self):
        try:
            self.qaction.setIcon(QIcon.ic("reader.png"))
        except Exception:
            pass
        self.qaction.triggered.connect(self.show_dialog)

    def apply_settings(self):
        pass

    # ------------------------------------------------------------------

    def show_dialog(self):
        rows = self.gui.library_view.selectionModel().selectedRows()
        if not rows:
            return error_dialog(self.gui, "No book selected",
                                "Select a book first.", show=True)
        if len(rows) != 1:
            return error_dialog(self.gui, "Select one book",
                                "Please select exactly one book.", show=True)
        book_id = self.gui.library_view.model().id(rows[0])

        db = self.gui.current_db.new_api
        fmts = [f.upper() for f in (db.formats(book_id) or [])]
        chosen = next((f for f in _FORMAT_ORDER if f in fmts),
                      fmts[0] if fmts else None)
        if not chosen:
            return error_dialog(
                self.gui, "No readable format",
                "This book has no EPUB/AZW3/MOBI/PDF/TXT format that "
                "calibre2audio can read.", show=True)
        path = db.format_abspath(book_id, chosen)
        if not path or not os.path.exists(path):
            return error_dialog(self.gui, "Format file missing",
                                "Could not locate the %s file on disk." % chosen,
                                show=True)

        mi = db.get_metadata(book_id)
        title = mi.title or "Unknown"
        authors = " & ".join(mi.authors) if mi.authors else "Unknown"

        cmd0 = self._resolve_command()
        if cmd0 is None:
            return error_dialog(
                self.gui, "calibre2audio not found",
                "Could not find the 'calibre2audio' command.\n\n"
                "Install it (e.g. 'uv tool install .' in the calibre2audio "
                "repo) or set its path under Preferences → Plugins "
                "→ Calibre2Audio → Customize plugin.", show=True)

        rec = resume_info(path)
        d = GenerateDialog(self.gui, title, authors, bool(rec), rec)
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        v = d.values()

        cmd = list(cmd0) + [
            "generate", "--file", path,
            "--title", title, "--author", authors,
            "--minutes", str(v["minutes"]),
            "--voice", v["voice"],
            "--speed", str(v["speed"]),
            "--device", "auto",
            "--print-path",
        ]
        if v["resume"]:
            cmd.append("--resume")
        else:
            cmd += ["--from", v["phrase"]]
        if v["output_dir"]:
            cmd += ["--out", v["output_dir"]]

        env = dict(os.environ)
        local_bin = os.path.expanduser("~/.local/bin")
        env["PATH"] = local_bin + os.pathsep + env.get("PATH", "")
        env["PYTHONUNBUFFERED"] = "1"

        pd = ProgressDialog(self.gui, cmd, env,
                            title="Generating audio: %s" % title)
        pd.exec()

        if pd.returncode == 0 and pd.output_path:
            if v["add_to_book"]:
                try:
                    db.add_format(book_id, "MP3", pd.output_path,
                                  replace=True, run_hooks=False)
                    self.gui.library_view.model().refresh_ids([book_id])
                except Exception as e:  # noqa: BLE001
                    error_dialog(self.gui, "Could not attach MP3", str(e),
                                 show=True)
            info_dialog(self.gui, "Audio ready",
                        "Saved:\n%s" % pd.output_path,
                        det_msg=pd.full_log, show=True)
        elif pd.returncode not in (0, None):
            error_dialog(self.gui, "Generation failed",
                         "calibre2audio exited with code %s." % pd.returncode,
                         det_msg=pd.full_log, show=True)

    # ------------------------------------------------------------------

    def _resolve_command(self):
        """Resolve the configured command to an executable argv, or None."""
        raw = (prefs["command"] or "").strip() or "calibre2audio"
        parts = shlex.split(raw)
        if not parts:
            return None
        exe = parts[0]
        if os.path.isabs(exe) or os.sep in exe:
            return parts if os.path.exists(exe) else None
        found = shutil.which(exe)
        if not found:
            cand = os.path.expanduser("~/.local/bin/" + exe)
            found = cand if os.path.exists(cand) else None
        return ([found] + parts[1:]) if found else None
