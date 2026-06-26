"""Plugin preferences and configuration widget."""

from qt.core import (QComboBox, QFormLayout, QLabel, QLineEdit, QSpinBox,
                     QVBoxLayout, QWidget)

from calibre.utils.config import JSONConfig

# Stored at ~/.config/calibre/plugins/calibre2audio.json
prefs = JSONConfig("plugins/calibre2audio")
prefs.defaults["command"] = "calibre2audio"
prefs.defaults["output_dir"] = ""   # empty -> CLI default (~/audiobooks)
prefs.defaults["voice"] = "af_heart"
prefs.defaults["minutes"] = 60

# Curated voices, mirroring calibre2audio.tts.VOICES (kept in sync by hand).
VOICES = [
    ("af_heart", "American English, female (warm) — default"),
    ("af_bella", "American English, female"),
    ("af_nicole", "American English, female (soft/ASMR)"),
    ("af_sarah", "American English, female"),
    ("am_michael", "American English, male"),
    ("am_fenrir", "American English, male (deep)"),
    ("am_puck", "American English, male (bright)"),
    ("bf_emma", "British English, female"),
    ("bf_isabella", "British English, female"),
    ("bm_george", "British English, male"),
    ("bm_fable", "British English, male"),
]


class ConfigWidget(QWidget):

    def __init__(self):
        QWidget.__init__(self)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)

        self.command_edit = QLineEdit(prefs["command"])
        self.command_edit.setToolTip(
            "Command used to run the calibre2audio CLI. Usually just "
            "'calibre2audio' if installed with 'uv tool install'. You may also "
            "give an absolute path, or a full command such as\n"
            "'uv run --project /path/to/calibre2audio calibre2audio'."
        )
        form.addRow("calibre2audio command:", self.command_edit)

        self.output_edit = QLineEdit(prefs["output_dir"])
        self.output_edit.setPlaceholderText("(default: ~/audiobooks)")
        form.addRow("Default output folder:", self.output_edit)

        self.voice_combo = QComboBox()
        for vid, desc in VOICES:
            self.voice_combo.addItem(f"{vid} — {desc}", vid)
        idx = self.voice_combo.findData(prefs["voice"])
        if idx >= 0:
            self.voice_combo.setCurrentIndex(idx)
        form.addRow("Default voice:", self.voice_combo)

        self.minutes_spin = QSpinBox()
        self.minutes_spin.setRange(1, 600)
        self.minutes_spin.setValue(int(prefs["minutes"]))
        self.minutes_spin.setSuffix(" min")
        form.addRow("Default length:", self.minutes_spin)

        note = QLabel(
            "This plugin requires the calibre2audio command-line tool to be "
            "installed separately (it provides the neural TTS engine).\n"
            "See: https://github.com/leechuck/calibre2audio"
        )
        note.setWordWrap(True)
        layout.addWidget(note)

    def save_settings(self):
        prefs["command"] = self.command_edit.text().strip() or "calibre2audio"
        prefs["output_dir"] = self.output_edit.text().strip()
        prefs["voice"] = self.voice_combo.currentData()
        prefs["minutes"] = int(self.minutes_spin.value())
