"""The 'Generate run audio' parameter dialog."""

import json
import os
from pathlib import Path

from qt.core import (QButtonGroup, QCheckBox, QDialog, QDialogButtonBox,
                     QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout,
                     QLabel, QLineEdit, QPlainTextEdit, QPushButton,
                     QRadioButton, QSpinBox, QVBoxLayout, QWidget)

from calibre.gui2 import warning_dialog

from calibre_plugins.calibre2audio.config import VOICES, prefs


def resume_info(book_path):
    """Best-effort read of the CLI's saved resume position for this file.

    The CLI keys --file runs as 'file:<resolved path>' in its state.json. We read
    it only to show the user whether a resume point exists; the actual resume is
    performed by the CLI itself, so a key mismatch is harmless.
    """
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    state = Path(base) / "calibre2audio" / "state.json"
    try:
        data = json.loads(state.read_text())
        key = "file:" + str(Path(book_path).resolve())
        return data.get("books", {}).get(key)
    except Exception:
        return None


class GenerateDialog(QDialog):

    def __init__(self, gui, title, authors, has_resume, resume_rec):
        QDialog.__init__(self, gui)
        self.setWindowTitle("Generate run audio")
        self.setMinimumWidth(560)
        layout = QVBoxLayout(self)

        head = QLabel("<b>%s</b><br>%s" % (title, authors))
        head.setWordWrap(True)
        layout.addWidget(head)

        # -- Start point -------------------------------------------------
        self.from_radio = QRadioButton("Start from a phrase I just read:")
        self.resume_radio = QRadioButton("Resume from the last export")
        grp = QButtonGroup(self)
        grp.addButton(self.from_radio)
        grp.addButton(self.resume_radio)

        layout.addWidget(self.from_radio)
        self.phrase_edit = QPlainTextEdit()
        self.phrase_edit.setPlaceholderText(
            "Paste a distinctive sentence exactly as it appears on your Kindle…")
        self.phrase_edit.setFixedHeight(70)
        layout.addWidget(self.phrase_edit)

        layout.addWidget(self.resume_radio)
        if has_resume and resume_rec:
            snippet = (resume_rec.get("snippet") or "").strip()
            self.resume_radio.setText(
                "Resume from the last export  (…%s)" % snippet[-60:])
            self.resume_radio.setEnabled(True)
        else:
            self.resume_radio.setEnabled(False)
            self.resume_radio.setText(
                "Resume from the last export  (no previous export of this book)")
        self.from_radio.setChecked(True)
        self.from_radio.toggled.connect(
            lambda on: self.phrase_edit.setEnabled(on))

        # -- Parameters --------------------------------------------------
        form = QFormLayout()
        layout.addLayout(form)

        self.minutes_spin = QSpinBox()
        self.minutes_spin.setRange(1, 600)
        self.minutes_spin.setValue(int(prefs["minutes"]))
        self.minutes_spin.setSuffix(" min")
        form.addRow("Run length:", self.minutes_spin)

        from qt.core import QComboBox
        self.voice_combo = QComboBox()
        for vid, desc in VOICES:
            self.voice_combo.addItem(f"{vid} — {desc}", vid)
        idx = self.voice_combo.findData(prefs["voice"])
        if idx >= 0:
            self.voice_combo.setCurrentIndex(idx)
        form.addRow("Voice:", self.voice_combo)

        self.speed_spin = QDoubleSpinBox()
        self.speed_spin.setRange(0.5, 2.0)
        self.speed_spin.setSingleStep(0.1)
        self.speed_spin.setValue(1.0)
        form.addRow("Speed:", self.speed_spin)

        out_row = QHBoxLayout()
        self.out_edit = QLineEdit(prefs["output_dir"])
        self.out_edit.setPlaceholderText("(default: ~/audiobooks)")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        out_row.addWidget(self.out_edit)
        out_row.addWidget(browse)
        form.addRow("Output folder:", out_row)

        self.add_check = QCheckBox(
            "Also attach the MP3 to this book in Calibre (as an MP3 format)")
        layout.addWidget(self.add_check)

        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        layout.addWidget(bb)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Choose output folder")
        if d:
            self.out_edit.setText(d)

    def _accept(self):
        if self.from_radio.isChecked() and not self.phrase_edit.toPlainText().strip():
            return warning_dialog(
                self, "Need a start phrase",
                "Type a phrase to start from, or choose 'Resume'.", show=True)
        self.accept()

    def values(self):
        return {
            "resume": self.resume_radio.isChecked(),
            "phrase": self.phrase_edit.toPlainText().strip(),
            "minutes": int(self.minutes_spin.value()),
            "voice": self.voice_combo.currentData(),
            "speed": round(float(self.speed_spin.value()), 2),
            "output_dir": self.out_edit.text().strip(),
            "add_to_book": self.add_check.isChecked(),
        }
